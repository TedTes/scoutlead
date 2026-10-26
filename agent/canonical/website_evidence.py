from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from shared.utils import normalize_url


GOOGLE_WEBSITE_SOURCES = {"google_places", "google_places_seed"}
STRUCTURED_LISTING_WEBSITE_SOURCES = GOOGLE_WEBSITE_SOURCES | {"openstreetmap"}
CONFIRMED_WEBSITE_SOURCE = "website_presence_check"
ENRICHED_WEBSITE_SOURCE = "company_website_seed"
NON_IDENTITY_NAME_TOKENS = {
    "and",
    "company",
    "contracting",
    "contractor",
    "home",
    "house",
    "inc",
    "ltd",
    "painting",
    "painter",
    "painters",
    "professional",
    "service",
    "services",
    "the",
    "toronto",
}
BLOCKED_WEBSITE_HOSTS = {
    "angi.com",
    "bbb.org",
    "craigslist.org",
    "facebook.com",
    "google.com",
    "google.ca",
    "homestars.com",
    "houzz.com",
    "instagram.com",
    "kijiji.ca",
    "linkedin.com",
    "mapquest.com",
    "thumbtack.com",
    "trustedpros.ca",
    "yelp.ca",
    "yelp.com",
    "yellowpages.ca",
}


@dataclass(frozen=True)
class TrustedWebsiteEvidence:
    url: str
    confidence: int


@dataclass(frozen=True)
class WebsiteOwnershipAssessment:
    url: str | None
    status: str
    confidence: int
    reason: str
    evidence: dict[str, Any]


def assess_website_ownership(
    *,
    source: str,
    payload: dict[str, Any],
    business_name: str,
    business_phone: str | None,
) -> WebsiteOwnershipAssessment | None:
    """Classify a candidate URL without invalidating unrelated business evidence."""
    source_key = source.strip().lower()
    candidate = _candidate_website_url(source_key, payload)
    if candidate is None:
        return None

    normalized = normalize_url(candidate)
    host = _host(normalized)
    evidence = {"candidate_url": candidate, "host": host, "source": source_key}
    scheme = urlparse(normalized or "").scheme.lower()
    if normalized is None or scheme not in {"http", "https"} or not host or "." not in host:
        return WebsiteOwnershipAssessment(
            url=None,
            status="failed",
            confidence=100,
            reason="Candidate website URL is not a valid public HTTP(S) URL.",
            evidence=evidence,
        )
    if _host_is_blocked(host):
        return WebsiteOwnershipAssessment(
            url=normalized,
            status="failed",
            confidence=100,
            reason="Candidate URL belongs to a marketplace, directory, or social platform.",
            evidence=evidence,
        )

    if source_key == ENRICHED_WEBSITE_SOURCE:
        enrichment = payload.get("website_enrichment")
        if not isinstance(enrichment, dict):
            return _uncertain(normalized, evidence, "Website inspection evidence is missing.")
        status = str(enrichment.get("availability_status") or "").strip().lower()
        inspected = enrichment.get("inspected_urls")
        if status in {"parked", "unavailable", "broken"}:
            return WebsiteOwnershipAssessment(
                url=normalized,
                status="failed",
                confidence=95,
                reason="Candidate website was unavailable, parked, or broken during inspection.",
                evidence={**evidence, "availability_status": status},
            )
        if not isinstance(inspected, list) or not inspected:
            return _uncertain(normalized, evidence, "Candidate website was not inspected.")
        if _enrichment_identity_matches(
            business_name=business_name,
            business_phone=business_phone,
            website_url=normalized,
            enrichment=enrichment,
        ):
            return WebsiteOwnershipAssessment(
                url=normalized,
                status="passed",
                confidence=95,
                reason="Website inspection matched the canonical business identity.",
                evidence={**evidence, "identity_method": "website_inspection"},
            )
        return WebsiteOwnershipAssessment(
            url=normalized,
            status="failed",
            confidence=95,
            reason="Website inspection conflicts with the canonical business identity.",
            evidence={**evidence, "identity_method": "website_inspection"},
        )

    if source_key == CONFIRMED_WEBSITE_SOURCE:
        presence = payload.get("website_presence")
        status = (
            str(presence.get("status") or "").strip().lower()
            if isinstance(presence, dict)
            else ""
        )
        if status not in {"active", "available", "website_found_during_confirmation"}:
            return _uncertain(
                normalized,
                evidence,
                "Website confirmation did not report a found website.",
            )
        return WebsiteOwnershipAssessment(
            url=normalized,
            status="passed",
            confidence=95,
            reason="The website-confirmation workflow bound this URL to the canonical business.",
            evidence={
                **evidence,
                "identity_method": "website_confirmation",
                "confirmation_attempted": bool(presence.get("confirmation_attempted")),
            },
        )

    is_curated_seed = str(payload.get("extraction_method") or "").strip().lower() == "seed_import"
    if source_key in STRUCTURED_LISTING_WEBSITE_SOURCES or is_curated_seed:
        identity_method = _listing_identity_method(
            payload=payload,
            business_name=business_name,
            business_phone=business_phone,
            website_url=normalized,
        )
        if identity_method is not None:
            return WebsiteOwnershipAssessment(
                url=normalized,
                status="passed",
                confidence=(
                    95
                    if source_key in GOOGLE_WEBSITE_SOURCES or is_curated_seed
                    else 90
                ),
                reason=(
                    "Curated seed fields bind this website to the canonical business."
                    if is_curated_seed
                    else "Structured provider fields bind this website to the canonical business."
                ),
                evidence={**evidence, "identity_method": identity_method},
            )
        return _uncertain(
            normalized,
            evidence,
            "The listing contains a website, but ownership could not be confirmed.",
        )

    return _uncertain(
        normalized,
        evidence,
        "The source is not approved to establish official website ownership.",
    )


def trusted_website_evidence(
    *,
    source: str,
    payload: dict[str, Any],
    business_name: str,
    business_phone: str | None,
) -> TrustedWebsiteEvidence | None:
    assessment = assess_website_ownership(
        source=source,
        payload=payload,
        business_name=business_name,
        business_phone=business_phone,
    )
    if assessment is None or assessment.status != "passed" or assessment.confidence < 90:
        return None
    return TrustedWebsiteEvidence(url=str(assessment.url), confidence=assessment.confidence)


def best_trusted_website_evidence(
    observations: Iterable[Any],
    *,
    business_name: str,
    business_phone: str | None,
) -> tuple[TrustedWebsiteEvidence, Any] | None:
    for observation in observations:
        evidence = trusted_website_evidence(
            source=str(observation.source or ""),
            payload=observation.raw_payload or {},
            business_name=business_name,
            business_phone=business_phone,
        )
        if evidence is not None:
            return evidence, observation
    return None


def _enrichment_identity_matches(
    *,
    business_name: str,
    business_phone: str | None,
    website_url: str | None,
    enrichment: dict[str, Any],
) -> bool:
    page_phones = {
        normalized
        for value in enrichment.get("phones") or []
        if (normalized := _phone_key(value))
    }
    business_phone_key = _phone_key(business_phone)
    if business_phone_key and page_phones and business_phone_key not in page_phones:
        return False
    if business_phone_key and business_phone_key in page_phones:
        return True

    host = urlparse(normalize_url(website_url) or "").hostname or ""
    domain_key = re.sub(r"[^a-z0-9]", "", host.lower().removeprefix("www."))
    name_key = re.sub(r"[^a-z0-9]", "", business_name.lower())
    if not domain_key or not name_key:
        return False
    meaningful_tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", business_name.lower())
        if len(token) >= 5 and token not in NON_IDENTITY_NAME_TOKENS
    }
    if any(token in domain_key for token in meaningful_tokens):
        return True
    return SequenceMatcher(None, name_key, domain_key).ratio() >= 0.6


def _public_website_url(value: str | None) -> str | None:
    normalized = normalize_url(value)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or not host or "." not in host:
        return None
    if _host_is_blocked(host):
        return None
    return normalized


def _candidate_website_url(source: str, payload: dict[str, Any]) -> str | None:
    if source == CONFIRMED_WEBSITE_SOURCE:
        presence = payload.get("website_presence")
        return (
            _first_text(presence, {"website_url", "websiteUri", "websiteUrl"})
            if isinstance(presence, dict)
            else None
        )
    if source == ENRICHED_WEBSITE_SOURCE:
        candidate = _first_text(payload, {"website_url", "websiteUri", "websiteUrl"})
        enrichment = payload.get("website_enrichment")
        inspected = enrichment.get("inspected_urls") if isinstance(enrichment, dict) else None
        return candidate or next(
            (str(value) for value in inspected or [] if isinstance(value, str) and value.strip()),
            None,
        )
    return _first_text(payload, {"website", "websiteUri", "website_url", "websiteUrl"})


def _listing_identity_method(
    *,
    payload: dict[str, Any],
    business_name: str,
    business_phone: str | None,
    website_url: str,
) -> str | None:
    business_phone_key = _phone_key(business_phone)
    listing_phones = {
        key
        for value in _all_text(
            payload,
            {"nationalPhoneNumber", "phone", "phone_number", "telephone"},
        )
        if (key := _phone_key(value))
    }
    if business_phone_key and business_phone_key in listing_phones:
        return "matching_phone"

    normalized_business = _name_key(business_name)
    listing_names = [
        _name_key(value)
        for value in _all_text(payload, {"displayName", "name", "title"})
    ]
    if normalized_business and any(
        value
        and (
            value == normalized_business
            or SequenceMatcher(None, normalized_business, value).ratio() >= 0.82
        )
        for value in listing_names
    ):
        return "matching_provider_name"

    host = _host(website_url)
    domain_key = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
    meaningful = _meaningful_name_tokens(business_name)
    if meaningful and any(token in domain_key for token in meaningful):
        return "matching_domain_name"
    return None


def _uncertain(url: str, evidence: dict[str, Any], reason: str) -> WebsiteOwnershipAssessment:
    return WebsiteOwnershipAssessment(
        url=url,
        status="uncertain",
        confidence=60,
        reason=reason,
        evidence=evidence,
    )


def _host(value: str | None) -> str:
    return (urlparse(value or "").hostname or "").lower().removeprefix("www.")


def _host_is_blocked(host: str) -> bool:
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_WEBSITE_HOSTS)


def _name_key(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("text") or value.get("name") or ""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split())


def _meaningful_name_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 5 and token not in NON_IDENTITY_NAME_TOKENS
    }


def _all_text(value: Any, keys: set[str]) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys:
                if isinstance(item, str) and item.strip():
                    found.append(item.strip())
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("name")
                    if isinstance(text, str) and text.strip():
                        found.append(text.strip())
            found.extend(_all_text(item, keys))
    elif isinstance(value, list):
        for item in value:
            found.extend(_all_text(item, keys))
    return found


def _first_text(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item.strip():
                return item.strip()
            nested = _first_text(item, keys)
            if nested:
                return nested
    elif isinstance(value, list):
        for item in value:
            nested = _first_text(item, keys)
            if nested:
                return nested
    return None


def _phone_key(value: Any) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 10:
        return None
    return digits[-10:]
