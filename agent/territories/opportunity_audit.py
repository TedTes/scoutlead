from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from canonical.normalization import normalize_business_name, normalize_domain
from canonical.repository import CanonicalRepository
from canonical.website_enrichment import SOURCE_NAME, EnrichmentSummary, enrich_business_pool
from db.models import (
    BusinessModel,
    CampaignModel,
    ContactModel,
    LeadModel,
    SourceObservationModel,
)
from shared.utils import normalize_url, utcnow
from tools.search import SearchTool
from tools.verify import EmailVerificationTool


WEBSITE_PRESENCE_SOURCE = "website_presence_check"
BLOCKED_CONFIRMATION_HOSTS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "yelp.",
    "yellowpages.",
    "google.com",
    "google.ca",
    "homestars.com",
    "houzz.",
)


@dataclass
class MissingWebsiteAudit:
    confirmed_absent: int = 0


class BusinessOpportunityAuditor:
    """Audit the exact businesses selected for a search or recurring delivery."""

    def __init__(
        self,
        *,
        session: Session,
        verifier: EmailVerificationTool | None,
        timeout_seconds: float,
        search: SearchTool | None = None,
        workers: int = 4,
    ) -> None:
        self.session = session
        self.verifier = verifier
        self.search = search
        self.timeout_seconds = timeout_seconds
        self.workers = max(1, workers)

    def audit_campaign(
        self,
        campaign_id: str,
        *,
        category: str | None,
        market: str | None,
    ) -> EnrichmentSummary:
        leads = list(
            self.session.scalars(
                select(LeadModel).where(LeadModel.campaign_id == campaign_id)
            )
        )
        business_ids = list(
            dict.fromkeys(lead.business_id for lead in leads if lead.business_id)
        )
        website_policy = self._campaign_website_policy(campaign_id)
        missing_website_audit = self._audit_missing_websites(leads)
        website_business_ids = business_ids
        if website_policy == "missing":
            website_business_ids = []
        summary = enrich_business_pool(
            self.session,
            category=category,
            market=market,
            limit=len(website_business_ids),
            include_with_email=True,
            refresh=True,
            verify=self.verifier is not None,
            timeout_seconds=self.timeout_seconds,
            max_pages_per_business=5,
            page_delay_seconds=0,
            commit_every=max(1, len(business_ids)),
            verifier=self.verifier,
            mark_attempted=True,
            workers=self.workers,
            business_ids=website_business_ids,
            opportunity_policy=website_policy,
        )
        summary.selected += missing_website_audit.confirmed_absent
        summary.inspected += missing_website_audit.confirmed_absent
        summary.with_digital_opportunity += missing_website_audit.confirmed_absent
        summary.high_digital_opportunity += missing_website_audit.confirmed_absent
        summary.written += missing_website_audit.confirmed_absent
        self._synchronize_leads(leads, business_ids)
        return summary

    def _campaign_website_policy(self, campaign_id: str) -> str:
        if not hasattr(self.session, "get"):
            return "any"
        campaign = self.session.get(CampaignModel, campaign_id)
        if campaign is None:
            return "any"
        return str((campaign.source_inputs or {}).get("website_policy") or "any")

    def _audit_missing_websites(self, leads: list[LeadModel]) -> MissingWebsiteAudit:
        canonical = CanonicalRepository(self.session)
        audit = MissingWebsiteAudit()
        changed = False
        seen_business_ids: set[str] = set()
        for lead in leads:
            if not lead.business_id or lead.business_id in seen_business_ids:
                continue
            seen_business_ids.add(lead.business_id)
            business = self.session.get(BusinessModel, lead.business_id)
            if business is None or business.website_url or lead.website_url:
                continue
            if _raw_text(lead.raw_sources, "businessStatus") != "OPERATIONAL":
                continue
            phone = business.phone or _raw_text(lead.raw_sources, "nationalPhoneNumber")
            maps_url = _raw_text(lead.raw_sources, "googleMapsUri") or _raw_text(
                lead.raw_sources, "source_url"
            )
            if not phone and not maps_url:
                continue

            website_url, confirmation_attempted, confirmation_query = self._confirm_website(
                business
            )
            if website_url:
                business.website_url = website_url
                business.domain = normalize_domain(website_url)
                lead.website_url = website_url
                raw = _website_presence_evidence(
                    business=business,
                    phone=phone,
                    maps_url=maps_url,
                    confirmation_query=confirmation_query,
                    status="website_found_during_confirmation",
                    label="Website found",
                    message="A credible business website was found during confirmation.",
                    score=0,
                    level="none",
                    confirmation_attempted=True,
                    website_url=website_url,
                )
                canonical.record_business_evidence(
                    business=business,
                    source=WEBSITE_PRESENCE_SOURCE,
                    raw=raw,
                )
                changed = True
                continue

            status = "no_website_found" if confirmation_attempted else "no_website_listed"
            label = "No website found" if confirmation_attempted else "No website listed"
            message = (
                "No business website was found in the Google profile or confirmation search."
                if confirmation_attempted
                else "Google Business Profile has no website listed."
            )
            points = 65 if confirmation_attempted else 35
            level = "high" if confirmation_attempted else "moderate"
            raw = _website_presence_evidence(
                business=business,
                phone=phone,
                maps_url=maps_url,
                confirmation_query=confirmation_query,
                status=status,
                label=label,
                message=message,
                score=points,
                level=level,
                confirmation_attempted=confirmation_attempted,
            )
            canonical.record_business_evidence(
                business=business,
                source=WEBSITE_PRESENCE_SOURCE,
                raw=raw,
            )
            if confirmation_attempted:
                audit.confirmed_absent += 1
            changed = True
        if changed:
            self.session.commit()
        return audit

    def _confirm_website(
        self,
        business: BusinessModel,
    ) -> tuple[str | None, bool, str]:
        location = business.address or business.geography or ""
        query = f'"{business.display_name}" "{location}" official website'
        if self.search is None or not self.search.is_configured:
            return None, False, query
        try:
            results = self.search.lookup(query, limit=5)
        except Exception:
            return None, False, query
        for result in results:
            website_url = _credible_business_website(
                result.url,
                result.title,
                business.display_name,
            )
            if website_url:
                return website_url, True, query
        return None, True, query

    def _synchronize_leads(
        self,
        leads: list[LeadModel],
        business_ids: list[str],
    ) -> None:
        if not business_ids:
            return
        observations = list(
            self.session.scalars(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.business_id.in_(business_ids),
                    SourceObservationModel.source.in_(
                        [SOURCE_NAME, WEBSITE_PRESENCE_SOURCE]
                    ),
                )
                .order_by(SourceObservationModel.observed_at.desc())
            )
        )
        latest_observation = {}
        for observation in observations:
            latest_observation.setdefault(observation.business_id, observation)

        contacts_by_business: dict[str, list[ContactModel]] = defaultdict(list)
        for contact in self.session.scalars(
            select(ContactModel).where(ContactModel.business_id.in_(business_ids))
        ):
            contacts_by_business[contact.business_id].append(contact)

        for lead in leads:
            if not lead.business_id:
                continue
            observation = latest_observation.get(lead.business_id)
            if observation is not None and not _has_observation(lead, observation.id):
                lead.raw_sources = [
                    *list(lead.raw_sources or []),
                    {
                        "source": observation.source,
                        "source_url": observation.source_url,
                        "source_observation_id": observation.id,
                        "raw": observation.raw_payload,
                    },
                ]
                flag_modified(lead, "raw_sources")

            contact = _best_contact(contacts_by_business.get(lead.business_id, []))
            if contact is None:
                continue
            lead.contact_id = contact.id
            lead.contact_email = contact.email
            lead.verification_status = contact.verification_status
            lead.verification_provider = contact.verification_provider
            lead.verification_checked_at = contact.verification_checked_at
            lead.verification_reason = contact.verification_reason
            lead.verification_score = contact.verification_score
            lead.verification_details = contact.verification_details
        self.session.commit()


def _best_contact(contacts: list[ContactModel]) -> ContactModel | None:
    candidates = [contact for contact in contacts if contact.email]
    if not candidates:
        return None
    status_rank = {
        "valid": 4,
        "risky": 3,
        "unverified": 2,
        "unknown": 1,
        "invalid": 0,
    }
    return max(
        candidates,
        key=lambda contact: (
            status_rank.get(contact.verification_status, 0),
            contact.verification_score or 0,
            contact.last_seen_at,
        ),
    )


def _has_observation(lead: LeadModel, observation_id: str) -> bool:
    return any(
        isinstance(source, dict)
        and source.get("source_observation_id") == observation_id
        for source in lead.raw_sources or []
    )


def _website_presence_evidence(
    *,
    business: BusinessModel,
    phone: str | None,
    maps_url: str | None,
    confirmation_query: str,
    status: str,
    label: str,
    message: str,
    score: int,
    level: str,
    confirmation_attempted: bool,
    website_url: str | None = None,
) -> dict:
    assessed_at = utcnow().isoformat()
    return {
        "external_id": f"{business.id}:website-presence",
        "query": confirmation_query,
        "source_url": website_url or maps_url,
        "website_presence": {
            "status": status,
            "label": label,
            "google_website_listed": False,
            "confirmation_attempted": confirmation_attempted,
            "confirmed_at": assessed_at,
            "phone": phone,
            "google_maps_url": maps_url,
            "website_url": website_url,
        },
        "digital_opportunity": {
            "version": 1,
            "score": score,
            "level": level,
            "assessed_at": assessed_at,
            "signals": [
                {
                    "key": status,
                    "message": message,
                    "points": score,
                    "source_url": website_url or maps_url,
                    "value": label,
                }
            ],
        },
    }


def _credible_business_website(
    value: str | None,
    result_title: str,
    business_name: str,
) -> str | None:
    url = normalize_url(value)
    if not url:
        return None
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    if not host or any(blocked in host for blocked in BLOCKED_CONFIRMATION_HOSTS):
        return None
    business_tokens = {
        token
        for token in normalize_business_name(business_name).split()
        if len(token) >= 3
    }
    result_text = f"{result_title} {host}".casefold()
    matching_tokens = sum(token in result_text for token in business_tokens)
    required_matches = min(2, len(business_tokens))
    return url if required_matches and matching_tokens >= required_matches else None


def _raw_text(sources: list[dict], key: str) -> str | None:
    stack: list[object] = list(sources)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for item_key, item in value.items():
                if item_key == key and isinstance(item, (str, int, float)):
                    text = str(item).strip()
                    if text:
                        return text
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return None


# Backward-compatible name for callers predating ordinary-search audits.
TerritoryOpportunityAuditor = BusinessOpportunityAuditor
