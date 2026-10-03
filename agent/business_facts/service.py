from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.repository import (
    BusinessFactKey,
    BusinessFactRepository,
    BusinessFactValue,
)
from db.models import BusinessModel, SourceObservationModel
from evaluation.digital_opportunity import opportunity_evidence_from_sources


RESOLVER_VERSION = 2


def reconcile_business_facts(session: Session, business_id: str) -> dict[str, Any]:
    business = session.get(BusinessModel, business_id)
    if business is None:
        return {}
    observations = list(
        session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
        )
    )
    resolved = _resolve_facts(business, observations)
    repository = BusinessFactRepository(session)
    for fact in resolved.values():
        repository.upsert(business.id, fact)
    return {key: fact.value for key, fact in resolved.items()}


def _resolve_facts(
    business: BusinessModel,
    observations: list[SourceObservationModel],
) -> dict[str, BusinessFactValue]:
    facts: dict[str, BusinessFactValue] = {}
    website = _website_status_fact(business, observations)
    if website is not None:
        facts[website.key.value] = website
    for resolver in (
        _quote_form_fact,
        _contact_form_fact,
        _google_rating_fact,
        _google_review_count_fact,
        _operational_fact,
    ):
        fact = resolver(observations)
        if fact is not None:
            facts[fact.key.value] = fact
    return facts


def _website_status_fact(
    business: BusinessModel,
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    candidates: list[BusinessFactValue] = []
    for observation in observations:
        payload = observation.raw_payload or {}
        status, confidence = _website_status_from_payload(payload)
        if status is not None:
            candidates.append(
                BusinessFactValue(
                    key=BusinessFactKey.WEBSITE_STATUS,
                    value=status,
                    observed_at=observation.observed_at,
                    source_observation_id=observation.id,
                    confidence=confidence,
                    resolver_version=RESOLVER_VERSION,
                )
            )
    if business.website_url:
        evidence = next(
            (
                observation
                for observation in observations
                if _payload_has_website(observation.raw_payload or {})
            ),
            None,
        )
        present = BusinessFactValue(
            key=BusinessFactKey.WEBSITE_STATUS,
            value="present",
            observed_at=(evidence.observed_at if evidence else business.updated_at),
            source_observation_id=evidence.id if evidence else None,
            confidence=100,
            resolver_version=RESOLVER_VERSION,
        )
        # A provider omitting websiteUri does not invalidate a URL already attached to
        # the canonical business. Only a direct availability check can supersede it.
        direct_failure = next(
            (
                candidate
                for candidate in candidates
                if candidate.value in {"unavailable", "parked"}
                and candidate.source_observation_id
                and any(
                    observation.id == candidate.source_observation_id
                    and observation.source == "website_presence_check"
                    for observation in observations
                )
                and _aware(candidate.observed_at) > _aware(present.observed_at)
            ),
            None,
        )
        return direct_failure or present
    if not candidates:
        latest_observation = observations[0] if observations else None
        return BusinessFactValue(
            key=BusinessFactKey.WEBSITE_STATUS,
            value="unknown",
            observed_at=(
                latest_observation.observed_at
                if latest_observation is not None
                else business.updated_at
            ),
            source_observation_id=(
                latest_observation.id if latest_observation is not None else None
            ),
            confidence=0,
            resolver_version=RESOLVER_VERSION,
        )
    conclusive = [
        fact
        for fact in candidates
        if fact.value in {"present", "missing", "unavailable", "parked"}
    ]
    pool = conclusive or candidates
    return max(pool, key=lambda fact: (_aware(fact.observed_at), fact.confidence))


def _website_status_from_payload(payload: dict[str, Any]) -> tuple[str | None, int]:
    presence = payload.get("website_presence")
    if isinstance(presence, dict):
        mapped = _map_website_status(str(presence.get("status") or ""))
        if mapped:
            return mapped
    enrichment = payload.get("website_enrichment")
    if isinstance(enrichment, dict):
        mapped = _map_website_status(str(enrichment.get("availability_status") or ""))
        if mapped:
            return mapped
    opportunity = opportunity_evidence_from_sources([payload])
    signals = opportunity.get("signals") if opportunity else None
    if isinstance(signals, list):
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            mapped = _map_website_status(str(signal.get("key") or ""))
            if mapped:
                return mapped
    if _payload_has_website(payload):
        return "present", 90
    raw_presence = _first_value(payload, {"website_presence_status"})
    mapped = _map_website_status(str(raw_presence or ""))
    return mapped or (None, 0)


def _map_website_status(value: str) -> tuple[str, int] | None:
    normalized = value.strip().lower()
    mapping = {
        "active": ("present", 100),
        "available": ("present", 100),
        "website_found_during_confirmation": ("present", 100),
        # A failed search is negative evidence, not proof that a site does not exist.
        "no_website_found": ("not_listed", 65),
        "no_website_listed": ("not_listed", 55),
        "missing": ("missing", 95),
        "unavailable": ("unavailable", 95),
        "website_unavailable": ("unavailable", 95),
        "parked": ("parked", 95),
        "website_parked": ("parked", 95),
        "website_unreachable": ("unknown", 30),
    }
    return mapping.get(normalized)


def _quote_form_fact(
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    for observation in observations:
        enrichment = (observation.raw_payload or {}).get("website_enrichment")
        if not isinstance(enrichment, dict) or not enrichment.get("inspected_urls"):
            continue
        value = bool(enrichment.get("has_quote_form") or enrichment.get("has_booking_form"))
        return BusinessFactValue(
            key=BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT,
            value=value,
            observed_at=observation.observed_at,
            source_observation_id=observation.id,
            confidence=100,
            resolver_version=RESOLVER_VERSION,
        )
    return None


def _contact_form_fact(
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    for observation in observations:
        enrichment = (observation.raw_payload or {}).get("website_enrichment")
        if not isinstance(enrichment, dict) or not enrichment.get("inspected_urls"):
            continue
        return BusinessFactValue(
            key=BusinessFactKey.CONTACT_FORM_PRESENT,
            value=bool(enrichment.get("has_contact_form")),
            observed_at=observation.observed_at,
            source_observation_id=observation.id,
            confidence=100,
            resolver_version=RESOLVER_VERSION,
        )
    return None


def _google_rating_fact(
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    return _number_fact(
        observations,
        key=BusinessFactKey.GOOGLE_RATING,
        field_names={"google_rating", "rating"},
    )


def _google_review_count_fact(
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    return _number_fact(
        observations,
        key=BusinessFactKey.GOOGLE_REVIEW_COUNT,
        field_names={"google_review_count", "userRatingCount", "review_count"},
    )


def _number_fact(
    observations: list[SourceObservationModel],
    *,
    key: BusinessFactKey,
    field_names: set[str],
) -> BusinessFactValue | None:
    for observation in observations:
        value = _first_value(observation.raw_payload or {}, field_names)
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if number is None:
            continue
        return BusinessFactValue(
            key=key,
            value=number,
            observed_at=observation.observed_at,
            source_observation_id=observation.id,
            confidence=95,
            resolver_version=RESOLVER_VERSION,
        )
    return None


def _operational_fact(
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    for observation in observations:
        value = _first_value(observation.raw_payload or {}, {"businessStatus"})
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if normalized not in {"OPERATIONAL", "CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
            continue
        return BusinessFactValue(
            key=BusinessFactKey.BUSINESS_OPERATIONAL,
            value=normalized == "OPERATIONAL",
            observed_at=observation.observed_at,
            source_observation_id=observation.id,
            confidence=100,
            resolver_version=RESOLVER_VERSION,
        )
    return None


def _payload_has_website(payload: dict[str, Any]) -> bool:
    value = _first_value(
        payload,
        {"websiteUri", "website_url", "websiteUrl", "official_website"},
    )
    return bool(str(value or "").strip())


def _first_value(value: Any, keys: set[str]) -> Any | None:
    for key, entry in _walk_items(value):
        if key in keys and entry not in (None, "", [], {}):
            return entry
    return None


def _walk_items(value: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, entry in value.items():
            yield str(key), entry
            yield from _walk_items(entry)
    elif isinstance(value, list):
        for entry in value:
            yield from _walk_items(entry)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
