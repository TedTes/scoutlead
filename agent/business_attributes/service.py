from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from business_attributes.repository import (
    BusinessAttributeKey,
    BusinessAttributeRepository,
    BusinessAttributeValue,
)
from business_attributes.freshness import attribute_expires_at
from canonical.normalization import normalize_domain
from canonical.website_evidence import (
    assess_website_ownership,
    best_trusted_website_evidence,
)
from db.models import (
    BusinessModel,
    LeadModel,
    BusinessAttributeModel,
)
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from seeding.batches import observation_is_quarantined
from shared.utils import normalize_url, utcnow


RESOLVER_VERSION = 4
GOOGLE_REPUTATION_SOURCES = frozenset({"google_places", "google_places_seed"})


def reconcile_business_attributes(session: Session, business_id: str) -> dict[str, Any]:
    business = session.get(BusinessModel, business_id)
    if business is None:
        return {}
    observations = [
        observation
        for observation in session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id == business_id,
                BusinessAttributeModel.row_type == "evidence",
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        )
        if not observation_is_quarantined(session, observation)
    ]
    ownership_confidence_by_observation: dict[str, int] = {}
    for observation in observations:
        assessment = assess_website_ownership(
            source=observation.source or "",
            payload=observation.raw_payload or {},
            business_name=business.display_name,
            business_phone=business.phone,
        )
        if assessment and assessment.status == "passed" and assessment.confidence >= 90:
            ownership_confidence_by_observation[observation.id] = assessment.confidence
    trusted_observation_ids = set(ownership_confidence_by_observation)
    trusted = best_trusted_website_evidence(
        [
            observation
            for observation in observations
            if observation.id in trusted_observation_ids
        ],
        business_name=business.display_name,
        business_phone=business.phone,
    )
    trusted_url = trusted[0].url if trusted is not None else None
    website_reconciled = bool(
        trusted_url
        and normalize_url(business.website_url) != normalize_url(trusted_url)
    )
    if website_reconciled:
        business.website_url = trusted_url
        business.domain = normalize_domain(trusted_url)
    resolved = _resolve_facts(
        business,
        observations,
        ownership_confidence_by_observation=ownership_confidence_by_observation,
    )
    repository = BusinessAttributeRepository(session)
    website_fact_changed = False
    for fact in resolved.values():
        _model, value_changed = repository.upsert_with_value_change(business.id, fact)
        if fact.key == BusinessAttributeKey.WEBSITE_STATUS:
            website_fact_changed = value_changed
    website_fact = resolved.get(BusinessAttributeKey.WEBSITE_STATUS.value)
    if website_fact is not None and (website_reconciled or website_fact_changed):
        _synchronize_lead_website_state(
            session,
            business=business,
            website_status=str(website_fact.value),
        )
    return {key: fact.value for key, fact in resolved.items()}


def _resolve_facts(
    business: BusinessModel,
    observations: list[BusinessAttributeModel],
    *,
    ownership_confidence_by_observation: dict[str, int],
) -> dict[str, BusinessAttributeValue]:
    facts: dict[str, BusinessAttributeValue] = {}
    website = _website_status_fact(
        business,
        observations,
        ownership_confidence_by_observation=ownership_confidence_by_observation,
    )
    if website is not None:
        facts[website.key.value] = website
    for resolver in (_google_rating_fact, _google_review_count_fact, _operational_fact):
        fact = resolver(observations)
        if fact is not None:
            facts[fact.key.value] = fact
    return facts


def _website_status_fact(
    business: BusinessModel,
    observations: list[BusinessAttributeModel],
    *,
    ownership_confidence_by_observation: dict[str, int],
) -> BusinessAttributeValue | None:
    candidates: list[BusinessAttributeValue] = []
    for observation in observations:
        payload = observation.raw_payload or {}
        status, confidence = _website_status_from_payload(payload)
        if status == "present":
            ownership_confidence = ownership_confidence_by_observation.get(observation.id)
            if ownership_confidence is None:
                continue
            confidence = min(confidence, ownership_confidence)
        if status is not None:
            candidates.append(
                BusinessAttributeValue(
                    key=BusinessAttributeKey.WEBSITE_STATUS,
                    value=status,
                    observed_at=observation.observed_at,
                    source_evidence_id=observation.id,
                    confidence=confidence,
                    expires_at=attribute_expires_at(
                        BusinessAttributeKey.WEBSITE_STATUS.value,
                        observation.observed_at,
                    ),
                    resolver_version=RESOLVER_VERSION,
                )
            )
    if business.website_url:
        evidence = next(
            (
                observation
                for observation in observations
                if observation.id in ownership_confidence_by_observation
                and _payload_has_website(observation.raw_payload or {})
            ),
            None,
        )
        if evidence is None:
            business.website_url = None
            business.domain = None
        else:
            present = BusinessAttributeValue(
                key=BusinessAttributeKey.WEBSITE_STATUS,
                value="present",
                observed_at=evidence.observed_at,
                source_evidence_id=evidence.id,
                confidence=ownership_confidence_by_observation[evidence.id],
                expires_at=attribute_expires_at(
                    BusinessAttributeKey.WEBSITE_STATUS.value,
                    evidence.observed_at,
                ),
                resolver_version=RESOLVER_VERSION,
            )
            # A provider omitting websiteUri does not invalidate a URL already attached to
            # the canonical business. Only a direct availability check can supersede it.
            direct_failure = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.value in {"unavailable", "parked"}
                    and candidate.source_evidence_id
                    and any(
                        observation.id == candidate.source_evidence_id
                        and observation.source == "website_presence_check"
                        for observation in observations
                    )
                    and _aware(candidate.observed_at) > _aware(present.observed_at)
                ),
                None,
            )
            return direct_failure or present
    if not candidates:
        return None
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
        if _verified_missing_website(presence):
            return "missing", 95
        mapped = _map_website_status(str(presence.get("status") or ""))
        if mapped:
            return mapped
    enrichment = payload.get("website_enrichment")
    if isinstance(enrichment, dict):
        enrichment_status = str(enrichment.get("availability_status") or "")
        if (
            enrichment_status.strip().lower() == "missing"
            and not enrichment.get("inspected_urls")
            and not _payload_has_website(payload)
        ):
            return "unknown", 0
        mapped = _map_website_status(enrichment_status)
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
        "verification_incomplete": ("unknown", 0),
        "not_checked": ("unknown", 0),
    }
    return mapping.get(normalized)


def _verified_missing_website(presence: dict[str, Any]) -> bool:
    """Distinguish a completed negative search from a listing omission.

    ``no_website_found`` historically covered both meanings.  New opportunity
    audits include their provider checks, so only a completed independent web
    search is strong enough to resolve the canonical status to ``missing``.
    Google omitting its website field remains ``not_listed`` and an incomplete
    check remains unknown.
    """

    if str(presence.get("status") or "").strip().lower() != "no_website_found":
        return False
    if not presence.get("confirmation_attempted"):
        return False
    checks = presence.get("confirmation_checks")
    if not isinstance(checks, list):
        return False
    return any(
        isinstance(check, dict)
        and str(check.get("provider") or "").strip().lower() == "configured_search"
        and str(check.get("status") or "").strip().lower() == "completed"
        for check in checks
    )


def _google_rating_fact(
    observations: list[BusinessAttributeModel],
) -> BusinessAttributeValue | None:
    return _number_fact(
        observations,
        key=BusinessAttributeKey.GOOGLE_RATING,
        field_names={"google_rating", "rating"},
        allowed_sources=GOOGLE_REPUTATION_SOURCES,
    )


def _google_review_count_fact(
    observations: list[BusinessAttributeModel],
) -> BusinessAttributeValue | None:
    return _number_fact(
        observations,
        key=BusinessAttributeKey.GOOGLE_REVIEW_COUNT,
        field_names={"google_review_count", "userRatingCount", "review_count"},
        allowed_sources=GOOGLE_REPUTATION_SOURCES,
    )


def _number_fact(
    observations: list[BusinessAttributeModel],
    *,
    key: BusinessAttributeKey,
    field_names: set[str],
    allowed_sources: frozenset[str] | None = None,
) -> BusinessAttributeValue | None:
    for observation in observations:
        if allowed_sources is not None and observation.source not in allowed_sources:
            continue
        value = _first_value(observation.raw_payload or {}, field_names)
        try:
            number = float(value) if value is not None else None
        except (TypeError, ValueError):
            number = None
        if number is None:
            continue
        return BusinessAttributeValue(
            key=key,
            value=number,
            observed_at=observation.observed_at,
            source_evidence_id=observation.id,
            confidence=95,
            expires_at=attribute_expires_at(key.value, observation.observed_at),
            resolver_version=RESOLVER_VERSION,
        )
    return None


def _operational_fact(
    observations: list[BusinessAttributeModel],
) -> BusinessAttributeValue | None:
    for observation in observations:
        value = _first_value(observation.raw_payload or {}, {"businessStatus"})
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if normalized not in {"OPERATIONAL", "CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"}:
            continue
        return BusinessAttributeValue(
            key=BusinessAttributeKey.BUSINESS_OPERATIONAL,
            value=normalized == "OPERATIONAL",
            observed_at=observation.observed_at,
            source_evidence_id=observation.id,
            confidence=100,
            expires_at=attribute_expires_at(
                BusinessAttributeKey.BUSINESS_OPERATIONAL.value,
                observation.observed_at,
            ),
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


def _synchronize_lead_website_state(
    session: Session,
    *,
    business: BusinessModel,
    website_status: str,
) -> None:
    for lead in session.scalars(
        select(LeadModel).where(LeadModel.business_id == business.id)
    ):
        changed = False
        if business.website_url and lead.website_url != business.website_url:
            lead.website_url = business.website_url
            changed = True
        if _replace_website_fact(lead.raw_sources, website_status):
            flag_modified(lead, "raw_sources")
            changed = True
        if changed:
            lead.updated_at = utcnow()


def _replace_website_fact(value: Any, website_status: str) -> bool:
    changed = False
    if isinstance(value, dict):
        attributes = value.get("business_attributes")
        if isinstance(attributes, dict):
            current = attributes.get("website_status")
            if isinstance(current, dict):
                if current.get("value") != website_status:
                    current["value"] = website_status
                    changed = True
            elif current != website_status:
                attributes["website_status"] = website_status
                changed = True
        for entry in value.values():
            changed = _replace_website_fact(entry, website_status) or changed
    elif isinstance(value, list):
        for entry in value:
            changed = _replace_website_fact(entry, website_status) or changed
    return changed
