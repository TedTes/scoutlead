"""Enrich canonical businesses from their public websites.

The script is intentionally narrow: it reads canonical businesses, inspects a
small set of same-domain homepage/contact/quote pages, then writes contacts and
website observations back through the canonical store.

Examples:
    python scripts/enrich_business_websites.py --category painting --market toronto --dry-run --limit 25
    python scripts/enrich_business_websites.py --category painting --market toronto --limit 25
    python scripts/enrich_business_websites.py --category painting --market toronto --limit 25 --verify
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
import json
import re
import time
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from canonical.normalization import normalize_domain  # noqa: E402
from canonical.repository import CanonicalRepository  # noqa: E402
from db.models import BusinessModel, ContactModel, SourceObservationModel  # noqa: E402
from db.session import Database  # noqa: E402
from shared.utils import normalize_text, normalize_url, truncate, utcnow  # noqa: E402
from tools.verify import EmailVerificationTool  # noqa: E402


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+?1[\s.-]?)?(?:\(?[2-9]\d{2}\)?[\s.-]?)?[2-9]\d{2}[\s.-]?\d{4}"
)
EVIDENCE_LINK_RE = re.compile(r"(contact|quote|estimate|about|service|pricing|request)", re.I)
QUOTE_TERMS = (
    "quote",
    "free quote",
    "request a quote",
    "estimate",
    "free estimate",
    "request estimate",
    "onsite estimate",
    "on-site estimate",
    "consultation",
)
SERVICE_TERMS = (
    "interior painting",
    "exterior painting",
    "residential painting",
    "commercial painting",
    "cabinet painting",
    "house painting",
    "deck staining",
    "drywall",
    "wallpaper",
)
COMMON_PATHS = (
    "/contact",
    "/quote",
    "/free-estimate",
    "/estimate",
    "/request-a-quote",
    "/request-estimate",
    "/contact-us",
    "/free-quote",
    "/services",
    "/about",
)
SOURCE_NAME = "company_website_seed"
PLACEHOLDER_EMAIL_DOMAINS = {
    "domain.com",
    "email.com",
    "example.ca",
    "example.com",
    "example.net",
    "example.org",
    "mail.com",
    "myemail.com",
    "mysite.com",
    "test.com",
    "yourdomain.ca",
    "yourdomain.com",
}
PLACEHOLDER_EMAIL_LOCALS = {
    "demo",
    "email",
    "example",
    "mail",
    "name",
    "sample",
    "test",
    "user",
    "username",
    "you",
    "your",
    "your-email",
    "your.email",
    "youremail",
}
LOW_QUALITY_EMAIL_LOCALS = {
    "abuse",
    "careers",
    "hostmaster",
    "hr",
    "jobs",
    "marketing",
    "postmaster",
    "privacy",
    "seo",
    "webmaster",
}
COMMON_MAILBOX_DOMAINS = {
    "aol.com",
    "bell.net",
    "gmail.com",
    "hotmail.ca",
    "hotmail.com",
    "icloud.com",
    "live.ca",
    "live.com",
    "me.com",
    "msn.com",
    "outlook.ca",
    "outlook.com",
    "rogers.com",
    "sympatico.ca",
    "yahoo.ca",
    "yahoo.com",
}


@dataclass(frozen=True)
class BusinessTarget:
    id: str
    display_name: str
    website_url: str | None
    phone: str | None
    address: str | None
    geography: str | None
    category_key: str | None
    market_key: str | None
    semantic_text: str | None


@dataclass
class WebsitePage:
    url: str
    title: str = ""
    description: str = ""
    text: str = ""
    html: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    has_form: bool = False
    has_quote_form: bool = False
    error: str = ""


@dataclass
class BusinessWebsiteEnrichment:
    business_id: str
    company_name: str
    website_url: str
    inspected_urls: list[str]
    emails: list[str]
    best_email: str | None
    phones: list[str]
    contact_name: str | None
    contact_role: str | None
    has_contact_form: bool
    has_quote_form: bool
    quote_signals: list[str]
    service_signals: list[str]
    source_url: str | None
    description: str
    errors: list[str]

    @property
    def found_signal(self) -> bool:
        return bool(
            self.emails
            or self.has_contact_form
            or self.has_quote_form
            or self.quote_signals
            or self.service_signals
        )


@dataclass
class EnrichmentSummary:
    dry_run: bool
    selected: int = 0
    inspected: int = 0
    reachable: int = 0
    with_email: int = 0
    with_quote_signal: int = 0
    with_contact_form: int = 0
    written: int = 0
    verified: int = 0
    failed: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


class WebsiteEnrichmentClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 12.0,
        max_pages_per_business: int = 5,
        page_delay_seconds: float = 0.2,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_pages_per_business = max(1, max_pages_per_business)
        self.page_delay_seconds = max(0.0, page_delay_seconds)

    def inspect(self, business: BusinessModel | BusinessTarget) -> BusinessWebsiteEnrichment:
        website_url = normalize_url(business.website_url)
        if not website_url:
            return _empty_enrichment(business, error="Business has no website URL.")

        pages: list[WebsitePage] = []
        errors: list[str] = []
        for url in self._candidate_urls(website_url):
            if len(pages) >= self.max_pages_per_business:
                break
            if url in {page.url for page in pages}:
                continue
            page = self._fetch_page(url)
            if page.error:
                errors.append(f"{url}: {page.error}")
                if url == website_url and website_url.startswith("https://"):
                    http_url = "http://" + website_url.removeprefix("https://")
                    fallback = self._fetch_page(http_url)
                    if not fallback.error:
                        page = fallback
                    else:
                        errors.append(f"{http_url}: {fallback.error}")
                if page.error:
                    continue
            pages.append(page)
            if self.page_delay_seconds:
                time.sleep(self.page_delay_seconds)

        if not pages:
            return _empty_enrichment(business, website_url=website_url, error="No website pages loaded.")

        extra_links = _ranked_evidence_links(
            links=[link for page in pages for link in page.links],
            base_url=pages[0].url,
        )
        for url in extra_links:
            if len(pages) >= self.max_pages_per_business:
                break
            if url in {page.url for page in pages}:
                continue
            page = self._fetch_page(url)
            if page.error:
                errors.append(f"{url}: {page.error}")
                continue
            pages.append(page)
            if self.page_delay_seconds:
                time.sleep(self.page_delay_seconds)

        return _enrichment_from_pages(business=business, website_url=website_url, pages=pages, errors=errors)

    def _candidate_urls(self, website_url: str) -> list[str]:
        base_url = _site_base_url(website_url)
        if not base_url:
            return [website_url]
        urls = [website_url, *[urljoin(base_url, path) for path in COMMON_PATHS]]
        return list(dict.fromkeys(urls))

    def _fetch_page(self, url: str) -> WebsitePage:
        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"user-agent": "soutlead/0.1 website-enrichment"},
            )
            response.raise_for_status()
        except Exception as exc:
            return WebsitePage(url=url, error=str(exc))

        content_type = str(response.headers.get("content-type", ""))
        if content_type and "html" not in content_type and "text" not in content_type:
            return WebsitePage(url=str(response.url), error=f"unsupported content type: {content_type}")

        html = response.text or ""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = normalize_text(soup.title.string if soup.title else "")
        description = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = normalize_text(str(meta["content"]))
        text = truncate(normalize_text(soup.get_text(" ")), 5000)
        links = [
            urljoin(str(response.url), str(link["href"]))
            for link in soup.find_all("a", href=True)
        ]
        form_text = " ".join(
            normalize_text(form.get_text(" "))
            for form in soup.find_all("form")
        ).lower()
        has_form = bool(soup.find("form"))
        return WebsitePage(
            url=str(response.url),
            title=title,
            description=description,
            text=text,
            html=html,
            emails=_extract_emails(html),
            phones=_extract_phones(text),
            links=sorted(set(links)),
            has_form=has_form,
            has_quote_form=has_form and _has_quote_signal(f"{title} {description} {text} {form_text}"),
        )


def enrich_business_pool(
    session: Session,
    *,
    category: str | None,
    market: str | None,
    source: str | None = None,
    limit: int = 25,
    dry_run: bool = False,
    include_with_email: bool = False,
    refresh: bool = False,
    verify: bool = False,
    timeout_seconds: float = 12.0,
    max_pages_per_business: int = 5,
    page_delay_seconds: float = 0.2,
    commit_every: int = 10,
    verifier: EmailVerificationTool | None = None,
    mark_attempted: bool = False,
    workers: int = 1,
    progress_every: int = 0,
) -> EnrichmentSummary:
    businesses = select_businesses(
        session,
        category=category,
        market=market,
        source=source,
        limit=limit,
        include_with_email=include_with_email,
        refresh=refresh,
    )
    summary = EnrichmentSummary(dry_run=dry_run, selected=len(businesses))
    client = WebsiteEnrichmentClient(
        timeout_seconds=timeout_seconds,
        max_pages_per_business=max_pages_per_business,
        page_delay_seconds=page_delay_seconds,
    )
    canonical = CanonicalRepository(session)
    writes_since_commit = 0

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_business = {
                executor.submit(client.inspect, _target_from_business(business)): business
                for business in businesses
            }
            for future in as_completed(future_to_business):
                business = future_to_business[future]
                try:
                    enrichment = future.result()
                except Exception as exc:
                    enrichment = _empty_enrichment(business, error=str(exc))
                writes_since_commit = _process_enrichment(
                    session=session,
                    canonical=canonical,
                    business=business,
                    enrichment=enrichment,
                    summary=summary,
                    dry_run=dry_run,
                    verify=verify,
                    verifier=verifier,
                    mark_attempted=mark_attempted,
                    writes_since_commit=writes_since_commit,
                    commit_every=commit_every,
                    progress_every=progress_every,
                )
    else:
        for business in businesses:
            enrichment = client.inspect(business)
            writes_since_commit = _process_enrichment(
                session=session,
                canonical=canonical,
                business=business,
                enrichment=enrichment,
                summary=summary,
                dry_run=dry_run,
                verify=verify,
                verifier=verifier,
                mark_attempted=mark_attempted,
                writes_since_commit=writes_since_commit,
                commit_every=commit_every,
                progress_every=progress_every,
            )

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return summary


def _process_enrichment(
    *,
    session: Session,
    canonical: CanonicalRepository,
    business: BusinessModel,
    enrichment: BusinessWebsiteEnrichment,
    summary: EnrichmentSummary,
    dry_run: bool,
    verify: bool,
    verifier: EmailVerificationTool | None,
    mark_attempted: bool,
    writes_since_commit: int,
    commit_every: int,
    progress_every: int,
) -> int:
    summary.inspected += 1
    if enrichment.inspected_urls:
        summary.reachable += 1
    if enrichment.best_email:
        summary.with_email += 1
    if enrichment.quote_signals or enrichment.has_quote_form:
        summary.with_quote_signal += 1
    if enrichment.has_contact_form:
        summary.with_contact_form += 1
    if enrichment.errors and not enrichment.inspected_urls:
        summary.failed += 1
        summary.errors.extend(_limited_errors(enrichment))
    if len(summary.examples) < 8 and enrichment.found_signal:
        summary.examples.append(_example(enrichment))
    if not enrichment.found_signal:
        summary.skipped += 1
    if progress_every and summary.inspected % progress_every == 0:
        print(
            (
                f"Progress: inspected {summary.inspected}/{summary.selected}, "
                f"written {summary.written}, emails {summary.with_email}, "
                f"quote signals {summary.with_quote_signal}, failed {summary.failed}"
            ),
            flush=True,
        )
    if dry_run or not (enrichment.found_signal or mark_attempted):
        return writes_since_commit

    link = canonical.upsert_from_discovery_result(
        company_name=business.display_name,
        website_url=business.website_url,
        contact_email=enrichment.best_email,
        geography=business.geography,
        description=enrichment.description,
        source=SOURCE_NAME,
        raw=_raw_payload(business, enrichment),
    )
    if verify and enrichment.best_email and link.contact_id:
        _verify_contact(
            session,
            canonical=canonical,
            verifier=verifier,
            contact_id=link.contact_id,
            email=enrichment.best_email,
            business=business,
        )
        summary.verified += 1
    summary.written += 1
    writes_since_commit += 1
    if writes_since_commit >= max(1, commit_every):
        session.commit()
        writes_since_commit = 0
    return writes_since_commit


def select_businesses(
    session: Session,
    *,
    category: str | None,
    market: str | None,
    source: str | None,
    limit: int,
    include_with_email: bool,
    refresh: bool,
) -> list[BusinessModel]:
    statement = select(BusinessModel).where(BusinessModel.website_url.is_not(None))
    if category:
        pattern = _like_pattern(category)
        statement = statement.where(
            or_(
                func.lower(BusinessModel.category_key).like(pattern),
                func.lower(BusinessModel.semantic_text).like(pattern),
                func.lower(BusinessModel.display_name).like(pattern),
            )
        )
    if market:
        pattern = _like_pattern(market)
        statement = statement.where(
            or_(
                func.lower(BusinessModel.market_key).like(pattern),
                func.lower(BusinessModel.geography).like(pattern),
                func.lower(BusinessModel.address).like(pattern),
            )
        )
    if source:
        pattern = _like_pattern(source)
        source_business_ids = select(SourceObservationModel.business_id).where(
            func.lower(SourceObservationModel.source).like(pattern)
        )
        statement = statement.where(BusinessModel.id.in_(source_business_ids))
    statement = statement.order_by(BusinessModel.last_seen_at.desc(), BusinessModel.display_name)

    if limit <= 0:
        return []

    businesses = list(session.scalars(statement))
    business_ids = [business.id for business in businesses]
    email_business_ids = _business_ids_with_email(session, business_ids)
    enriched_business_ids = _business_ids_with_website_observation(session, business_ids)

    selected: list[BusinessModel] = []
    for business in businesses:
        if not include_with_email and business.id in email_business_ids:
            continue
        if not refresh and business.id in enriched_business_ids:
            continue
        selected.append(business)
        if len(selected) >= limit:
            break
    return selected


def _target_from_business(business: BusinessModel) -> BusinessTarget:
    return BusinessTarget(
        id=business.id,
        display_name=business.display_name,
        website_url=business.website_url,
        phone=business.phone,
        address=business.address,
        geography=business.geography,
        category_key=business.category_key,
        market_key=business.market_key,
        semantic_text=business.semantic_text,
    )


def _enrichment_from_pages(
    *,
    business: BusinessModel | BusinessTarget,
    website_url: str,
    pages: list[WebsitePage],
    errors: list[str],
) -> BusinessWebsiteEnrichment:
    combined_text = " ".join(f"{page.title} {page.description} {page.text}" for page in pages)
    emails = sorted({email for page in pages for email in page.emails})
    phones = sorted({phone for page in pages for phone in page.phones})
    quote_signals = _term_hits(combined_text, QUOTE_TERMS)
    service_signals = _term_hits(combined_text, SERVICE_TERMS)
    has_contact_form = any(page.has_form for page in pages)
    has_quote_form = any(page.has_quote_form for page in pages)
    contact_name, contact_role = _extract_contact_name(combined_text)
    best_email = _best_email(emails, business.website_url)
    source_url = _best_source_url(pages)
    description = _description(
        business=business,
        pages=pages,
        best_email=best_email,
        has_contact_form=has_contact_form,
        has_quote_form=has_quote_form,
        quote_signals=quote_signals,
        service_signals=service_signals,
    )
    return BusinessWebsiteEnrichment(
        business_id=business.id,
        company_name=business.display_name,
        website_url=website_url,
        inspected_urls=[page.url for page in pages],
        emails=emails,
        best_email=best_email,
        phones=phones,
        contact_name=contact_name,
        contact_role=contact_role,
        has_contact_form=has_contact_form,
        has_quote_form=has_quote_form,
        quote_signals=quote_signals,
        service_signals=service_signals,
        source_url=source_url,
        description=description,
        errors=errors,
    )


def _raw_payload(business: BusinessModel, enrichment: BusinessWebsiteEnrichment) -> dict[str, Any]:
    query = f"website enrichment for {business.category_key or 'business'} {business.market_key or business.geography or ''}"
    signals = ["public website inspected"]
    if enrichment.best_email:
        signals.append("email found")
    if enrichment.has_contact_form:
        signals.append("contact form found")
    if enrichment.has_quote_form:
        signals.append("quote or estimate form found")
    signals.extend(enrichment.quote_signals)
    signals.extend(enrichment.service_signals)
    signals = list(dict.fromkeys(signal for signal in signals if signal))
    return {
        "company_name": business.display_name,
        "website_url": business.website_url,
        "contact_email": enrichment.best_email,
        "contact_name": enrichment.contact_name,
        "contact_role": enrichment.contact_role,
        "contact_phone": business.phone or (enrichment.phones[0] if enrichment.phones else None),
        "phone": business.phone or (enrichment.phones[0] if enrichment.phones else None),
        "geography": business.geography,
        "address": business.address,
        "description": enrichment.description,
        "source": SOURCE_NAME,
        "source_url": enrichment.source_url or business.website_url,
        "external_id": f"website_enrichment:{business.id}",
        "query": query,
        "search_query": query,
        "signals": signals,
        "source_input": {
            "query": query,
            "geography": business.geography,
            "source_type": "website_enrichment",
            "source_request_prompt": query,
            "source_request_intent": {
                "business_category": business.category_key or "public business",
                "location": business.market_key or business.geography or "",
                "required_signals": signals,
                "search_query": query,
            },
        },
        "source_request_intent": {
            "business_category": business.category_key or "public business",
            "location": business.market_key or business.geography or "",
            "required_signals": signals,
            "search_query": query,
        },
        "website_enrichment": {
            "inspected_at": utcnow().isoformat(),
            "inspected_urls": enrichment.inspected_urls,
            "emails": enrichment.emails,
            "best_email": enrichment.best_email,
            "phones": enrichment.phones,
            "has_contact_form": enrichment.has_contact_form,
            "has_quote_form": enrichment.has_quote_form,
            "quote_signals": enrichment.quote_signals,
            "service_signals": enrichment.service_signals,
            "errors": enrichment.errors[:5],
        },
    }


def _verify_contact(
    session: Session,
    *,
    canonical: CanonicalRepository,
    verifier: EmailVerificationTool | None,
    contact_id: str,
    email: str,
    business: BusinessModel,
) -> None:
    tool = verifier or EmailVerificationTool(provider="syntax")
    result = tool.run(
        {
            "email": email,
            "phone": business.phone,
            "business": {
                "id": business.id,
                "name": business.display_name,
                "website_url": business.website_url,
            },
        }
    )
    data = result.data if isinstance(result.data, dict) else {}
    canonical.apply_contact_verification(
        contact_id=contact_id,
        status=str(data.get("status") or data.get("verdict") or "unknown"),
        provider=result.provider,
        checked_at=utcnow(),
        reason=str(data.get("reason") or "Website enrichment verification."),
        score=int(data.get("score") or result.confidence or 0),
        details=data.get("details") if isinstance(data.get("details"), dict) else {},
    )
    session.flush()


def _extract_emails(html: str) -> list[str]:
    cleaned = html.replace("[at]", "@").replace("(at)", "@").replace(" at ", "@")
    emails = []
    for match in EMAIL_RE.findall(cleaned):
        email = match.strip(".,;:()[]{}<>\"'").lower()
        if _email_is_usable(email):
            emails.append(email)
    return sorted(set(emails))[:20]


def _extract_phones(text: str) -> list[str]:
    phones = []
    for match in PHONE_RE.findall(text):
        digits = re.sub(r"\D+", "", match)
        if len(digits) == 10:
            phones.append(f"{digits[:3]}-{digits[3:6]}-{digits[6:]}")
        elif len(digits) == 11 and digits.startswith("1"):
            phones.append(f"{digits[1:4]}-{digits[4:7]}-{digits[7:]}")
    return sorted(set(phones))[:10]


def _extract_contact_name(text: str) -> tuple[str | None, str | None]:
    role_terms = "owner|founder|president|principal|proprietor|operator"
    patterns = [
        rf"\b({role_terms})[:\s,-]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})",
        rf"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,2}})[,\s-]+({role_terms})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        first, second = match.group(1), match.group(2)
        if first.lower() in role_terms.split("|"):
            role, name = first, second
        else:
            name, role = first, second
        if _looks_like_person_name(name):
            return name, role.title()
    return None, None


def _looks_like_person_name(value: str) -> bool:
    blocked = {"contact us", "free estimate", "request quote", "home stars", "google review"}
    normalized = value.strip().lower()
    if normalized in blocked:
        return False
    return 2 <= len(value.split()) <= 3 or value.istitle()


def _best_email(emails: list[str], website_url: str | None) -> str | None:
    if not emails:
        return None
    eligible_emails = [
        email for email in emails if _email_is_usable_for_business(email, website_url)
    ]
    if not eligible_emails:
        return None
    business_domain = normalize_domain(website_url)
    ranked = sorted(
        eligible_emails,
        key=lambda email: (
            _email_rank(email),
            1 if business_domain and email.endswith(f"@{business_domain}") else 0,
            -len(email),
        ),
        reverse=True,
    )
    return ranked[0]


def _email_rank(email: str) -> int:
    local = email.split("@", 1)[0]
    if any(term in local for term in ("owner", "founder", "president", "principal")):
        return 90
    if re.fullmatch(r"[a-z]{2,}[._-][a-z]{2,}", local):
        return 80
    if any(term in local for term in ("hello", "info", "office", "contact", "team")):
        return 70
    if any(term in local for term in ("sales", "support", "admin")):
        return 55
    if any(term in local for term in ("noreply", "no-reply", "privacy")):
        return 10
    return 60


def _email_is_usable(email: str) -> bool:
    if not email or "@" not in email:
        return False
    local, domain = email.split("@", 1)
    if not local or not domain or "." not in domain:
        return False
    if domain.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")):
        return False
    if any(term in local for term in ("noreply", "no-reply")):
        return False
    if _email_local_is_low_quality(local):
        return False
    return not _email_is_placeholder(email)


def _email_is_usable_for_business(email: str, website_url: str | None) -> bool:
    return _email_is_usable(email) and _email_matches_business(email, website_url)


def _email_is_low_quality_for_business(email: str | None, website_url: str | None) -> bool:
    if not email:
        return False
    return not _email_is_usable_for_business(email, website_url)


def _email_local_is_low_quality(local: str) -> bool:
    normalized = local.lower().strip()
    if normalized in LOW_QUALITY_EMAIL_LOCALS:
        return True
    return any(
        normalized.startswith(f"{term}.") or normalized.startswith(f"{term}-")
        for term in LOW_QUALITY_EMAIL_LOCALS
    )


def _email_is_placeholder(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    local, domain = email.lower().split("@", 1)
    local = local.strip()
    domain = domain.strip().strip(".")
    if not local or not domain:
        return False
    if domain in PLACEHOLDER_EMAIL_DOMAINS:
        return True
    if "example" in domain:
        return True
    return local in PLACEHOLDER_EMAIL_LOCALS


def _email_matches_business(email: str, website_url: str | None) -> bool:
    email_domain = _domain_from_email(email)
    if not email_domain:
        return False
    if email_domain in COMMON_MAILBOX_DOMAINS:
        return True
    business_domain = normalize_domain(website_url)
    if not business_domain:
        return True
    return (
        email_domain == business_domain
        or email_domain.endswith(f".{business_domain}")
        or business_domain.endswith(f".{email_domain}")
    )


def _domain_from_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.lower().split("@", 1)[1].strip().strip(".")
    return domain or None


def cleanup_placeholder_emails(session: Session, *, dry_run: bool = False) -> dict[str, int]:
    bad_emails_by_business: dict[str, set[str]] = defaultdict(set)
    observations_changed = 0
    observations = session.execute(
        select(SourceObservationModel, BusinessModel)
        .join(BusinessModel, BusinessModel.id == SourceObservationModel.business_id)
        .where(SourceObservationModel.source == SOURCE_NAME)
    )
    for observation, business in observations:
        raw_payload = observation.raw_payload or {}
        for email in _payload_email_values(raw_payload):
            if _email_is_low_quality_for_business(email, business.website_url):
                bad_emails_by_business[business.id].add(email.lower())
        cleaned_payload = _clean_placeholder_emails_from_payload(raw_payload, business.website_url)
        if cleaned_payload == raw_payload:
            continue
        observations_changed += 1
        if not dry_run:
            observation.raw_payload = cleaned_payload
            flag_modified(observation, "raw_payload")

    contacts_changed = 0
    contacts_deleted = 0
    contacts = session.execute(
        select(ContactModel, BusinessModel)
        .join(BusinessModel, BusinessModel.id == ContactModel.business_id)
        .where(ContactModel.email.is_not(None))
    )
    for contact, business in contacts:
        is_placeholder = _email_is_placeholder(contact.email)
        email = str(contact.email or "").lower()
        if not is_placeholder and email not in bad_emails_by_business.get(business.id, set()):
            continue
        if not is_placeholder and contact.verification_status == "valid":
            continue
        contacts_changed += 1
        if not any([contact.name, contact.role, contact.phone]):
            if not dry_run:
                session.delete(contact)
            contacts_deleted += 1
            continue
        if not dry_run:
            contact.email = None
            contact.verification_status = "unverified"
            contact.verification_provider = None
            contact.verification_checked_at = None
            contact.verification_reason = "Placeholder email removed."
            contact.verification_score = None
            contact.verification_details = None

    if dry_run:
        session.rollback()
    else:
        session.commit()
    return {
        "contacts_changed": contacts_changed,
        "contacts_deleted": contacts_deleted,
        "observations_changed": observations_changed,
    }


def _payload_email_values(payload: dict[str, Any]) -> list[str]:
    emails: list[str] = []
    for key in ("contact_email", "email"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            emails.append(value.strip().lower())
    enrichment = payload.get("website_enrichment")
    if isinstance(enrichment, dict):
        best_email = enrichment.get("best_email")
        if isinstance(best_email, str) and best_email.strip():
            emails.append(best_email.strip().lower())
        raw_emails = enrichment.get("emails")
        if isinstance(raw_emails, list):
            emails.extend(email.strip().lower() for email in raw_emails if isinstance(email, str))
    return sorted(set(emails))


def _clean_placeholder_emails_from_payload(
    payload: dict[str, Any],
    website_url: str | None,
) -> dict[str, Any]:
    cleaned = dict(payload)
    for key in ("contact_email", "email"):
        if _email_is_low_quality_for_business(str(cleaned.get(key) or ""), website_url):
            cleaned[key] = None
    enrichment = cleaned.get("website_enrichment")
    if isinstance(enrichment, dict):
        cleaned_enrichment = dict(enrichment)
        if _email_is_low_quality_for_business(str(cleaned_enrichment.get("best_email") or ""), website_url):
            cleaned_enrichment["best_email"] = None
        emails = cleaned_enrichment.get("emails")
        if isinstance(emails, list):
            cleaned_enrichment["emails"] = [
                email
                for email in emails
                if isinstance(email, str) and _email_is_usable_for_business(email, website_url)
            ]
        cleaned["website_enrichment"] = cleaned_enrichment
    return cleaned


def _ranked_evidence_links(links: list[str], base_url: str) -> list[str]:
    base_domain = normalize_domain(base_url)
    ranked: list[tuple[int, str]] = []
    for link in links:
        if not link.startswith(("http://", "https://")):
            continue
        if normalize_domain(link) != base_domain:
            continue
        if not EVIDENCE_LINK_RE.search(link):
            continue
        ranked.append((_link_priority(link), link))
    return [link for _, link in sorted(set(ranked), key=lambda item: (item[0], item[1]))]


def _link_priority(link: str) -> int:
    path = urlparse(link).path.lower()
    if "contact" in path:
        return 0
    if "quote" in path or "estimate" in path or "request" in path:
        return 1
    if "about" in path:
        return 2
    if "service" in path:
        return 3
    return 4


def _best_source_url(pages: list[WebsitePage]) -> str | None:
    for page in pages:
        if page.emails:
            return page.url
    for page in pages:
        if page.has_quote_form or page.has_form:
            return page.url
    return pages[0].url if pages else None


def _description(
    *,
    business: BusinessModel | BusinessTarget,
    pages: list[WebsitePage],
    best_email: str | None,
    has_contact_form: bool,
    has_quote_form: bool,
    quote_signals: list[str],
    service_signals: list[str],
) -> str:
    evidence = []
    if best_email:
        evidence.append("public email")
    if has_quote_form:
        evidence.append("quote or estimate form")
    elif has_contact_form:
        evidence.append("contact form")
    evidence.extend(quote_signals[:3])
    evidence.extend(service_signals[:4])
    excerpt = truncate(
        normalize_text(" ".join(page.description or page.text for page in pages if page.text)),
        700,
    )
    parts = [
        f"{business.display_name} website enrichment",
        f"found {', '.join(dict.fromkeys(evidence))}" if evidence else "found public website evidence",
        f"from {len(pages)} inspected page{'s' if len(pages) != 1 else ''}.",
        excerpt,
    ]
    return normalize_text(" ".join(part for part in parts if part))


def _term_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _has_quote_signal(text: str) -> bool:
    return bool(_term_hits(text, QUOTE_TERMS))


def _business_ids_with_email(session: Session, business_ids: list[str]) -> set[str]:
    if not business_ids:
        return set()
    return set(
        session.scalars(
            select(ContactModel.business_id).where(
                ContactModel.business_id.in_(business_ids),
                ContactModel.email.is_not(None),
            )
        )
    )


def _business_ids_with_website_observation(session: Session, business_ids: list[str]) -> set[str]:
    if not business_ids:
        return set()
    return set(
        session.scalars(
            select(SourceObservationModel.business_id).where(
                SourceObservationModel.business_id.in_(business_ids),
                SourceObservationModel.source == SOURCE_NAME,
            )
        )
    )


def _empty_enrichment(
    business: BusinessModel | BusinessTarget,
    *,
    website_url: str | None = None,
    error: str,
) -> BusinessWebsiteEnrichment:
    description = (
        f"{business.display_name} website enrichment attempted; "
        f"no usable website evidence was loaded. Error: {error}"
    )
    return BusinessWebsiteEnrichment(
        business_id=business.id,
        company_name=business.display_name,
        website_url=website_url or business.website_url or "",
        inspected_urls=[],
        emails=[],
        best_email=None,
        phones=[],
        contact_name=None,
        contact_role=None,
        has_contact_form=False,
        has_quote_form=False,
        quote_signals=[],
        service_signals=[],
        source_url=None,
        description=description,
        errors=[error],
    )


def _limited_errors(enrichment: BusinessWebsiteEnrichment) -> list[str]:
    return [f"{enrichment.company_name}: {error}" for error in enrichment.errors[:2]]


def _example(enrichment: BusinessWebsiteEnrichment) -> dict[str, Any]:
    return {
        "company": enrichment.company_name,
        "best_email": enrichment.best_email,
        "quote_signals": enrichment.quote_signals[:4],
        "service_signals": enrichment.service_signals[:4],
        "contact_form": enrichment.has_contact_form,
        "quote_form": enrichment.has_quote_form,
        "pages": enrichment.inspected_urls[:4],
    }


def _site_base_url(value: str) -> str | None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


def _like_pattern(value: str) -> str:
    return f"%{value.strip().lower()}%"


def print_summary(summary: EnrichmentSummary) -> None:
    print("Business website enrichment")
    print(f"Dry run: {'yes' if summary.dry_run else 'no'}")
    print(f"Selected: {summary.selected}")
    print(f"Inspected: {summary.inspected}")
    print(f"Reachable: {summary.reachable}")
    print(f"With email: {summary.with_email}")
    print(f"With quote/estimate signal: {summary.with_quote_signal}")
    print(f"With contact form: {summary.with_contact_form}")
    print(f"Written: {summary.written}")
    print(f"Verified: {summary.verified}")
    print(f"Skipped no signal: {summary.skipped}")
    print(f"Failed: {summary.failed}")
    if summary.examples:
        print()
        print("Examples:")
        for example in summary.examples:
            print(f"  - {example['company']}")
            if example.get("best_email"):
                print(f"    email: {example['best_email']}")
            if example.get("quote_signals"):
                print(f"    quote signals: {', '.join(example['quote_signals'])}")
            if example.get("service_signals"):
                print(f"    service signals: {', '.join(example['service_signals'])}")
    if summary.errors:
        print()
        print("Errors:")
        for error in summary.errors[:20]:
            print(f"  - {error}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    database = Database(settings.database_url)
    session = next(database.session())
    try:
        if args.cleanup_placeholder_emails:
            cleanup = cleanup_placeholder_emails(session, dry_run=args.dry_run)
            print("Placeholder email cleanup")
            print(f"Contacts changed: {cleanup['contacts_changed']}")
            print(f"Contacts deleted: {cleanup['contacts_deleted']}")
            print(f"Observations changed: {cleanup['observations_changed']}")
            print()
        verifier = None
        if args.verify:
            verifier = EmailVerificationTool(
                provider=settings.contact_verification_provider,
                endpoint=settings.email_verification_endpoint,
                api_key=settings.email_verification_api_key,
                bouncer_api_key=settings.bouncer_api_key,
                bouncer_api_endpoint=settings.bouncer_api_endpoint,
                zerobounce_api_key=settings.zerobounce_api_key,
                zerobounce_api_endpoint=settings.zerobounce_api_endpoint,
                timeout_seconds=settings.request_timeout_seconds,
            )
        summary = enrich_business_pool(
            session,
            category=args.category,
            market=args.market,
            source=args.source,
            limit=args.limit,
            dry_run=args.dry_run,
            include_with_email=args.include_with_email,
            refresh=args.refresh,
            verify=args.verify,
            timeout_seconds=args.timeout_seconds,
            max_pages_per_business=args.max_pages_per_business,
            page_delay_seconds=args.page_delay_seconds,
            commit_every=args.commit_every,
            verifier=verifier,
            mark_attempted=args.mark_attempted,
            workers=args.workers,
            progress_every=args.progress_every,
        )
    finally:
        session.close()

    if args.json:
        print(json.dumps(asdict(summary), indent=2, sort_keys=True, default=str))
        return
    print_summary(summary)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich canonical businesses from public websites.")
    parser.add_argument("--category", help="Case-insensitive category/semantic text filter.")
    parser.add_argument("--market", help="Case-insensitive market/geography/address filter.")
    parser.add_argument("--source", help="Case-insensitive source-observation filter.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum businesses to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect sites without DB writes.")
    parser.add_argument(
        "--include-with-email",
        action="store_true",
        help="Include businesses that already have at least one contact email.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=f"Re-inspect businesses that already have {SOURCE_NAME} observations.",
    )
    parser.add_argument("--verify", action="store_true", help="Verify extracted email using configured provider.")
    parser.add_argument("--timeout-seconds", type=float, default=12.0)
    parser.add_argument("--max-pages-per-business", type=int, default=5)
    parser.add_argument("--page-delay-seconds", type=float, default=0.2)
    parser.add_argument("--commit-every", type=int, default=10)
    parser.add_argument(
        "--mark-attempted",
        action="store_true",
        help="Write an observation even when no email/form/signal is found, so later batches skip it.",
    )
    parser.add_argument("--workers", type=int, default=1, help="Concurrent website inspections.")
    parser.add_argument("--progress-every", type=int, default=0, help="Print progress every N inspected businesses.")
    parser.add_argument(
        "--cleanup-placeholder-emails",
        action="store_true",
        help="Remove fake, template, off-domain, and low-quality website emails before running.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
