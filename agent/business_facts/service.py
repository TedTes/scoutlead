from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from business_facts.repository import (
    BusinessFactKey,
    BusinessFactRepository,
    BusinessFactValue,
)
from business_facts.claims import FactClaim, FactClaimRepository
from business_facts.freshness import fact_expires_at
from canonical.normalization import normalize_domain
from canonical.website_evidence import (
    best_trusted_website_evidence,
    trusted_website_evidence,
)
from db.models import BusinessModel, LeadModel, SourceObservationModel
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from quality.fact_policy import FactQualityPolicyService
from seeding.batches import observation_is_quarantined
from shared.utils import utcnow


RESOLVER_VERSION = 3


def reconcile_business_facts(session: Session, business_id: str) -> dict[str, Any]:
    business = session.get(BusinessModel, business_id)
    if business is None:
        return {}
    observations = [
        observation
        for observation in session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
        )
        if not observation_is_quarantined(session, observation)
    ]
    trusted = best_trusted_website_evidence(
        observations,
        business_name=business.display_name,
        business_phone=business.phone,
    )
    website_promoted = business.website_url is None and trusted is not None
    if website_promoted:
        business.website_url = trusted[0].url
        business.domain = normalize_domain(trusted[0].url)
    claim_repository = FactClaimRepository(session)
    for observation in observations:
        for claim in _claims_from_observation(business, observation):
            claim_repository.record(claim)
    claims = claim_repository.current_for_business(business.id, now=utcnow())
    resolved = _resolve_facts(business, observations)
    resolved = {
        key: _attach_claim_resolution(fact, claims)
        for key, fact in resolved.items()
    }
    repository = BusinessFactRepository(session)
    website_fact_changed = False
    for fact in resolved.values():
        model, value_changed = repository.upsert_with_value_change(business.id, fact)
        FactQualityPolicyService(session).evaluate(model, commit=False)
        if fact.key == BusinessFactKey.WEBSITE_STATUS:
            website_fact_changed = value_changed
    website_fact = resolved.get(BusinessFactKey.WEBSITE_STATUS.value)
    if website_fact is not None and (website_promoted or website_fact_changed):
        _synchronize_lead_website_state(
            session,
            business=business,
            website_status=str(website_fact.value),
        )
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


def _claims_from_observation(
    business: BusinessModel,
    observation: SourceObservationModel,
) -> list[FactClaim]:
    payload = observation.raw_payload or {}
    values: list[BusinessFactValue] = []
    status, confidence = _website_status_from_payload(payload)
    if status == "present" and trusted_website_evidence(
        source=observation.source,
        payload=payload,
        business_name=business.display_name,
        business_phone=business.phone,
    ) is None:
        status = None
    if status is not None:
        values.append(
            BusinessFactValue(
                key=BusinessFactKey.WEBSITE_STATUS,
                value=status,
                observed_at=observation.observed_at,
                source_observation_id=observation.id,
                confidence=confidence,
                expires_at=fact_expires_at(
                    BusinessFactKey.WEBSITE_STATUS.value,
                    observation.observed_at,
                ),
                resolver_version=RESOLVER_VERSION,
            )
        )
    for resolver in (
        _quote_form_fact,
        _contact_form_fact,
        _google_rating_fact,
        _google_review_count_fact,
        _operational_fact,
    ):
        value = resolver([observation])
        if value is not None:
            values.append(value)
    return [
        FactClaim(
            business_id=business.id,
            fact_key=value.key.value,
            value=value.value,
            source_observation_id=observation.id,
            confidence=value.confidence,
            extractor="business_fact_resolver",
            extractor_version=RESOLVER_VERSION,
            observed_at=value.observed_at,
            expires_at=value.expires_at
            or fact_expires_at(value.key.value, value.observed_at),
        )
        for value in values
    ]


def _attach_claim_resolution(
    fact: BusinessFactValue,
    claims: list,
) -> BusinessFactValue:
    supporting = [
        claim
        for claim in claims
        if claim.fact_key == fact.key.value and claim.value == fact.value
    ]
    competing = [
        claim
        for claim in claims
        if claim.fact_key == fact.key.value
        and claim.value != fact.value
        and claim.confidence >= 90
    ]
    state = (
        "unknown"
        if fact.value == "unknown"
        else "conflicted"
        if competing and fact.confidence >= 90
        else "confirmed"
        if fact.confidence >= 90
        else "probable"
    )
    value = "unknown" if state == "conflicted" else fact.value
    confidence = 0 if state == "conflicted" else fact.confidence
    return BusinessFactValue(
        key=fact.key,
        value=value,
        observed_at=fact.observed_at,
        source_observation_id=fact.source_observation_id,
        confidence=confidence,
        resolution_state=state,
        supporting_claim_ids=tuple(claim.id for claim in supporting),
        quality_state="staged",
        quality_policy_version=1,
        expires_at=fact.expires_at,
        resolver_version=fact.resolver_version,
    )


def _website_status_fact(
    business: BusinessModel,
    observations: list[SourceObservationModel],
) -> BusinessFactValue | None:
    candidates: list[BusinessFactValue] = []
    for observation in observations:
        payload = observation.raw_payload or {}
        status, confidence = _website_status_from_payload(payload)
        if status == "present" and trusted_website_evidence(
            source=observation.source,
            payload=payload,
            business_name=business.display_name,
            business_phone=business.phone,
        ) is None:
            continue
        if status is not None:
            candidates.append(
                BusinessFactValue(
                    key=BusinessFactKey.WEBSITE_STATUS,
                    value=status,
                    observed_at=observation.observed_at,
                    source_observation_id=observation.id,
                    confidence=confidence,
                    expires_at=fact_expires_at(
                        BusinessFactKey.WEBSITE_STATUS.value,
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
            expires_at=fact_expires_at(
                BusinessFactKey.WEBSITE_STATUS.value,
                evidence.observed_at if evidence else business.updated_at,
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
            expires_at=fact_expires_at(
                BusinessFactKey.WEBSITE_STATUS.value,
                latest_observation.observed_at
                if latest_observation is not None
                else business.updated_at,
            ),
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
            expires_at=fact_expires_at(
                BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
                observation.observed_at,
            ),
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
            expires_at=fact_expires_at(
                BusinessFactKey.CONTACT_FORM_PRESENT.value,
                observation.observed_at,
            ),
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
            expires_at=fact_expires_at(key.value, observation.observed_at),
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
            expires_at=fact_expires_at(
                BusinessFactKey.BUSINESS_OPERATIONAL.value,
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
        facts = value.get("business_facts")
        if isinstance(facts, dict):
            current = facts.get("website_status")
            if isinstance(current, dict):
                if current.get("value") != website_status:
                    current["value"] = website_status
                    changed = True
            elif current != website_status:
                facts["website_status"] = website_status
                changed = True
        for entry in value.values():
            changed = _replace_website_fact(entry, website_status) or changed
    elif isinstance(value, list):
        for entry in value:
            changed = _replace_website_fact(entry, website_status) or changed
    return changed
