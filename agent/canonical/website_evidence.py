from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from shared.utils import normalize_url


GOOGLE_WEBSITE_SOURCES = {"google_places", "google_places_seed"}
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
    "facebook.com",
    "google.com",
    "google.ca",
    "homestars.com",
    "instagram.com",
    "linkedin.com",
    "yelp.ca",
    "yelp.com",
    "yellowpages.ca",
}


@dataclass(frozen=True)
class TrustedWebsiteEvidence:
    url: str
    confidence: int


def trusted_website_evidence(
    *,
    source: str,
    payload: dict[str, Any],
    business_name: str,
    business_phone: str | None,
) -> TrustedWebsiteEvidence | None:
    source_key = source.strip().lower()
    candidate: str | None = None
    confidence = 0

    if source_key in GOOGLE_WEBSITE_SOURCES:
        candidate = _first_text(payload, {"websiteUri", "website_url", "websiteUrl"})
        confidence = 100
    elif source_key == CONFIRMED_WEBSITE_SOURCE:
        presence = payload.get("website_presence")
        if not isinstance(presence, dict):
            return None
        status = str(presence.get("status") or "").strip().lower()
        if status not in {"active", "available", "website_found_during_confirmation"}:
            return None
        candidate = _first_text(presence, {"website_url", "websiteUri", "websiteUrl"})
        confidence = 100
    elif source_key == ENRICHED_WEBSITE_SOURCE:
        enrichment = payload.get("website_enrichment")
        if not isinstance(enrichment, dict):
            return None
        status = str(enrichment.get("availability_status") or "").strip().lower()
        inspected = enrichment.get("inspected_urls")
        if status in {"parked", "unavailable", "broken"} or not isinstance(inspected, list) or not inspected:
            return None
        candidate = _first_text(payload, {"website_url", "websiteUri", "websiteUrl"})
        candidate = candidate or next(
            (str(value) for value in inspected if isinstance(value, str) and value.strip()),
            None,
        )
        if not _enrichment_identity_matches(
            business_name=business_name,
            business_phone=business_phone,
            website_url=candidate,
            enrichment=enrichment,
        ):
            return None
        confidence = 90
    else:
        return None

    normalized = _public_website_url(candidate)
    if normalized is None:
        return None
    return TrustedWebsiteEvidence(url=normalized, confidence=confidence)


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
    if any(host == blocked or host.endswith(f".{blocked}") for blocked in BLOCKED_WEBSITE_HOSTS):
        return None
    return normalized


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
