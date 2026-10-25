from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.repository import fact_value
from db.models import (
    BusinessFactModel,
    FactClaimModel,
    SignalDefinitionModel,
    SourceObservationModel,
)
from business_validation.repository import ValidationRepository, ValidationResult
from shared.errors import ConflictError, NotFoundError
from shared.utils import utcnow
from signal_collection.service import extract_signal_value
from source_observations.integrity import evaluate_observation_integrity


VALIDATOR_VERSION = 3
GOOGLE_SOURCES = {"google_places", "google_places_seed"}
COLLECTOR_SOURCES = {
    "website_http": {"company_website_signal"},
    "website_dom": {"company_website_signal"},
    "pagespeed_mobile": {"pagespeed_mobile"},
    "domain_rdap": {"domain_rdap"},
    "google_places": GOOGLE_SOURCES,
}
SCORE_KEYS = {
    "mobile_performance_score",
    "accessibility_score",
    "best_practices_score",
    "seo_score",
    "website_quality_score",
}
NONNEGATIVE_KEYS = {
    "google_review_count",
    "domain_age_days",
    "lcp_ms",
    "cls_score",
    "inp_ms",
    "tbt_ms",
    "translated_page_count",
}
WEBSITE_STATUSES = {"present", "missing", "unavailable", "parked", "unknown"}
WEBSITE_EVIDENCE_KEYS = {
    "contact_form_present",
    "quote_or_booking_form_present",
    "uses_https",
    "mobile_viewport_present",
    "primary_cta_present",
    "click_to_call_present",
    "online_payment_or_financing_present",
    "service_area_pages_present",
}


@dataclass(frozen=True)
class SignalValidationDecision:
    status: str
    quality_state: str
    confidence: int
    reason: str
    evidence: list[dict[str, Any]]


class SignalValidationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def validate(
        self,
        signal_definition_id: str,
        *,
        expected_version: int,
        business_ids: list[str],
    ) -> dict[str, int]:
        definition = self.session.get(SignalDefinitionModel, signal_definition_id)
        if definition is None:
            raise NotFoundError(
                "signal definition not found",
                {"signal_definition_id": signal_definition_id},
            )
        if definition.status != "active":
            raise ConflictError("Only active signal definitions can be validated")
        if definition.version != expected_version:
            raise ConflictError(
                "Signal validation job uses an outdated definition version",
                {"expected": expected_version, "current": definition.version},
            )

        summary = {
            "requested": len(business_ids),
            "validated": 0,
            "published": 0,
            "needs_review": 0,
            "rejected": 0,
            "missing": 0,
        }
        for business_id in dict.fromkeys(business_ids):
            fact = self.session.scalar(
                select(BusinessFactModel).where(
                    BusinessFactModel.business_id == business_id,
                    BusinessFactModel.signal_definition_id == definition.id,
                )
            )
            claim = self.session.scalar(
                select(FactClaimModel)
                .where(
                    FactClaimModel.business_id == business_id,
                    FactClaimModel.signal_definition_id == definition.id,
                )
                .order_by(
                    FactClaimModel.observed_at.desc(),
                    FactClaimModel.confidence.desc(),
                )
                .limit(1)
            )
            if fact is None or claim is None:
                summary["missing"] += 1
                continue

            decision = self._decision(definition, fact, claim)
            fact.quality_state = decision.quality_state
            fact.quality_policy_version = VALIDATOR_VERSION
            ValidationRepository(self.session).record(
                ValidationResult(
                    business_id=business_id,
                    source_item_id=None,
                    source_observation_id=claim.source_observation_id,
                    validation_type=_validation_type(definition.key),
                    status=decision.status,
                    confidence=decision.confidence,
                    reason=decision.reason,
                    evidence=decision.evidence,
                    validator=f"signal_claim_policy:{definition.version}",
                    validator_version=VALIDATOR_VERSION,
                    observed_at=utcnow(),
                    expires_at=claim.expires_at,
                )
            )
            summary["validated"] += 1
            if decision.quality_state == "published":
                summary["published"] += 1
            elif decision.quality_state == "rejected":
                summary["rejected"] += 1
            else:
                summary["needs_review"] += 1

        self.session.commit()
        return summary

    def _decision(
        self,
        definition: SignalDefinitionModel,
        fact: BusinessFactModel,
        claim: FactClaimModel,
    ) -> SignalValidationDecision:
        observation = self.session.get(
            SourceObservationModel,
            claim.source_observation_id,
        )
        failures: list[str] = []
        review_reasons: list[str] = []
        evidence: list[dict[str, Any]] = []

        def check(name: str, passed: bool, detail: str) -> None:
            evidence.append({"check": name, "passed": passed, "detail": detail})
            if not passed:
                failures.append(detail)

        expected_sources = COLLECTOR_SOURCES.get(definition.collector_key or "")
        integrity = evaluate_observation_integrity(
            observation,
            expected_business_id=claim.business_id,
            expected_sources=expected_sources,
            now=utcnow(),
        )
        evidence.extend(integrity.evidence)
        failures.extend(integrity.failures)
        review_reasons.extend(integrity.warnings)
        if observation is not None:
            extracted = extract_signal_value(definition, observation.raw_payload or {})
            reproducible = extracted is not None and _values_equal(extracted, claim.value)
            check(
                "extractor_replay",
                reproducible,
                (
                    "Stored observation reproduces the claim value."
                    if reproducible
                    else "Stored observation does not reproduce the claim value."
                ),
            )
            if (
                observation.source == "company_website_signal"
                and definition.key in WEBSITE_EVIDENCE_KEYS
            ):
                evidence_valid, evidence_detail = _website_evidence_check(
                    definition.key,
                    claim.value,
                    observation.raw_payload or {},
                )
                check("website_evidence", evidence_valid, evidence_detail)

        value_valid, value_reason = _valid_value(definition, claim.value)
        check("value_constraints", value_valid, value_reason)
        fact_matches = _values_equal(fact_value(fact), claim.value)
        check(
            "resolved_fact_link",
            fact_matches and fact.source_observation_id == claim.source_observation_id,
            (
                "Resolved fact matches the newest claim and observation."
                if fact_matches and fact.source_observation_id == claim.source_observation_id
                else "Resolved fact does not match the newest claim and observation."
            ),
        )

        now = utcnow()
        if _aware(claim.expires_at) < _aware(now):
            review_reasons.append("Claim evidence is stale.")
        minimum_confidence = int((definition.config or {}).get("minimum_confidence", 90))
        if claim.confidence < minimum_confidence:
            review_reasons.append(
                f"Claim confidence {claim.confidence}% is below {minimum_confidence}%."
            )
        if fact.resolution_state == "conflicted" or self._has_conflict(definition, claim):
            review_reasons.append("Current high-confidence claims disagree.")
        if str((definition.config or {}).get("validation_mode") or "") == "manual":
            review_reasons.append("Signal definition requires manual validation.")

        if failures:
            return SignalValidationDecision(
                status="failed",
                quality_state="rejected",
                confidence=0,
                reason=" ".join(dict.fromkeys(failures)),
                evidence=evidence,
            )
        if review_reasons:
            return SignalValidationDecision(
                status="uncertain",
                quality_state="staged",
                confidence=min(claim.confidence, integrity.confidence),
                reason=" ".join(dict.fromkeys(review_reasons)),
                evidence=evidence,
            )
        return SignalValidationDecision(
            status="passed",
            quality_state="published",
            confidence=min(claim.confidence, integrity.confidence),
            reason="Claim passed source, extraction, value, freshness, and conflict checks.",
            evidence=evidence,
        )

    def _has_conflict(
        self,
        definition: SignalDefinitionModel,
        newest: FactClaimModel,
    ) -> bool:
        claims = self.session.scalars(
            select(FactClaimModel).where(
                FactClaimModel.business_id == newest.business_id,
                FactClaimModel.signal_definition_id == definition.id,
                FactClaimModel.id != newest.id,
                FactClaimModel.expires_at >= newest.observed_at,
                FactClaimModel.confidence >= 90,
            )
        )
        return any(not _values_equal(claim.value, newest.value) for claim in claims)


def _valid_value(
    definition: SignalDefinitionModel,
    value: Any,
) -> tuple[bool, str]:
    if definition.value_type == "boolean":
        valid = isinstance(value, bool)
        return valid, "Value is a boolean." if valid else "Value is not a boolean."
    if definition.value_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        valid = valid and isfinite(float(value))
        if valid and definition.key in SCORE_KEYS:
            valid = 0 <= float(value) <= 100
        elif valid and definition.key == "google_rating":
            valid = 0 <= float(value) <= 5
        elif valid and definition.key in NONNEGATIVE_KEYS:
            valid = float(value) >= 0
        return (
            valid,
            "Numeric value is within its allowed range."
            if valid
            else "Numeric value is outside its allowed range.",
        )
    if definition.value_type == "text":
        valid = isinstance(value, str) and bool(value.strip())
        if valid and definition.key == "website_status":
            valid = value in WEBSITE_STATUSES
        return (
            valid,
            "Text value is allowed." if valid else "Text value is empty or unsupported.",
        )
    return False, f"Unsupported signal value type {definition.value_type!r}."


def _website_evidence_check(
    signal_key: str,
    value: Any,
    payload: dict[str, Any],
) -> tuple[bool, str]:
    enrichment = payload.get("website_enrichment")
    if not isinstance(enrichment, dict):
        return False, "Website signal has no enrichment evidence."
    inspection = enrichment.get("inspection")
    evidence_by_signal = enrichment.get("signal_evidence")
    if not isinstance(inspection, dict) or not isinstance(evidence_by_signal, dict):
        return False, "Website signal is missing structured inspection evidence."
    pages = inspection.get("pages")
    if not isinstance(pages, list) or not pages:
        return False, "Website signal has no successfully inspected pages."
    evidence = evidence_by_signal.get(signal_key)
    if not isinstance(evidence, list):
        return False, f"Website signal {signal_key!r} has no evidence entry."
    if value is True and not evidence:
        return False, f"Positive website signal {signal_key!r} has no matching element."
    if value is False and inspection.get("complete") is not True:
        return False, f"Negative website signal {signal_key!r} came from an incomplete DOM crawl."
    return True, (
        f"Website signal {signal_key!r} is backed by {len(evidence)} matching element(s)."
        if value is True
        else f"Website signal {signal_key!r} was absent from a complete DOM crawl."
    )


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def _validation_type(key: str) -> str:
    candidate = f"signal:{key}"
    if len(candidate) <= 64:
        return candidate
    return f"signal:{sha256(key.encode('utf-8')).hexdigest()[:57]}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
