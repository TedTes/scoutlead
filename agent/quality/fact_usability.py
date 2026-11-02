from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.eligibility import (
    DEFAULT_MINIMUM_FACT_CONFIDENCE,
    UNKNOWN_TEXT_VALUES,
)
from business_facts.repository import fact_value
from business_facts.attribute_scoring import score_attribute
from db.models import (
    BusinessFactModel,
    SignalDefinitionModel,
    SourceObservationModel,
    ValidationResultModel,
)
from shared.utils import utcnow
from source_observations.contracts import expected_sources_for
from source_observations.integrity import evaluate_observation_integrity


FACT_USABILITY_POLICY_VERSION = 2


@dataclass(frozen=True)
class FactUsabilityDecision:
    useful: bool
    reason: str


@dataclass
class FactUsabilitySummary:
    dry_run: bool
    checked: int = 0
    retained: int = 0
    published: int = 0
    deleted: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    deleted_by_key: dict[str, int] = field(default_factory=dict)


def assess_fact_usability(
    fact: BusinessFactModel,
    *,
    definition: SignalDefinitionModel | None,
    observation: SourceObservationModel | None,
    validation: ValidationResultModel | None,
    now: datetime | None = None,
) -> FactUsabilityDecision:
    """Decide whether a canonical fact is safe and immediately usable.

    Historical evidence is intentionally outside this decision. Claims and source
    observations remain the audit/recovery layer; ``business_facts`` is the small
    current read model consumed by matching and the admin UI.
    """

    checked_at = now or utcnow()
    if definition is None or definition.status not in {"active", "derived"}:
        return FactUsabilityDecision(False, "missing_or_inactive_definition")
    if fact.quality_state == "rejected":
        return FactUsabilityDecision(False, "rejected")
    if fact.resolution_state != "confirmed":
        return FactUsabilityDecision(False, "unconfirmed")
    value = fact_value(fact)
    if value is None or (
        isinstance(value, str) and value.strip().lower() in UNKNOWN_TEXT_VALUES
    ):
        return FactUsabilityDecision(False, "unknown_value")
    if fact.attribute_score is None:
        return FactUsabilityDecision(False, "unscored")
    if fact.expires_at is None or _aware(fact.expires_at) <= _aware(checked_at):
        return FactUsabilityDecision(False, "stale")

    config = definition.config or {}
    minimum_confidence = int(
        config.get("minimum_confidence", DEFAULT_MINIMUM_FACT_CONFIDENCE)
    )
    if fact.confidence < minimum_confidence:
        return FactUsabilityDecision(False, "low_confidence")

    expected_sources = expected_sources_for(
        fact_key=fact.fact_key,
        collector_key=definition.collector_key,
    )
    integrity = evaluate_observation_integrity(
        observation,
        expected_business_id=fact.business_id,
        expected_sources=expected_sources,
        now=checked_at,
    )
    if integrity.status != "passed":
        return FactUsabilityDecision(False, "invalid_observation")

    if bool(config.get("requires_validation", True)):
        valid = bool(
            validation is not None
            and validation.status == "passed"
            and validation.confidence >= minimum_confidence
            and validation.source_observation_id == fact.source_observation_id
            and _aware(validation.expires_at) > _aware(checked_at)
        )
        if not valid:
            return FactUsabilityDecision(False, "missing_validation")
    return FactUsabilityDecision(True, "useful")


def clean_canonical_facts(
    session: Session,
    *,
    apply: bool = False,
    limit: int = 100_000,
) -> FactUsabilitySummary:
    """Publish useful facts and delete unusable canonical rows.

    This never deletes source observations, claims, or change history.
    """

    now = utcnow()
    facts = list(
        session.scalars(
            select(BusinessFactModel).order_by(BusinessFactModel.id).limit(limit)
        )
    )
    summary = FactUsabilitySummary(dry_run=not apply)
    if not facts:
        return summary

    definitions = {
        row.id: row for row in session.scalars(select(SignalDefinitionModel))
    }
    observation_ids = {
        fact.source_observation_id for fact in facts if fact.source_observation_id
    }
    observations = {
        row.id: row
        for row in session.scalars(
            select(SourceObservationModel).where(
                SourceObservationModel.id.in_(observation_ids)
            )
        )
    }
    business_ids = {fact.business_id for fact in facts}
    validations = list(
        session.scalars(
            select(ValidationResultModel)
            .where(ValidationResultModel.business_id.in_(business_ids))
            .order_by(
                ValidationResultModel.observed_at.desc(),
                ValidationResultModel.created_at.desc(),
                ValidationResultModel.id.desc(),
            )
        )
    )
    latest_validations: dict[tuple[str, str], ValidationResultModel] = {}
    for validation in validations:
        latest_validations.setdefault(
            (validation.business_id, validation.validation_type), validation
        )

    for fact in facts:
        summary.checked += 1
        definition = definitions.get(fact.signal_definition_id or "")
        if fact.attribute_score is None and definition is not None:
            scored = score_attribute(
                fact.fact_key,
                fact_value(fact),
                opportunity_direction=definition.opportunity_direction,
                config=definition.config,
            )
            if scored.score is not None:
                fact.attribute_score = scored.score
                fact.score_version = scored.version
                fact.score_reason = scored.reason
        decision = assess_fact_usability(
            fact,
            definition=definition,
            observation=observations.get(fact.source_observation_id or ""),
            validation=latest_validations.get(
                (fact.business_id, f"signal:{fact.fact_key}")
            ),
            now=now,
        )
        summary.reasons[decision.reason] = summary.reasons.get(decision.reason, 0) + 1
        if decision.useful:
            if fact.quality_state == "published" and (
                fact.quality_policy_version >= FACT_USABILITY_POLICY_VERSION
            ):
                summary.retained += 1
            else:
                summary.published += 1
                if apply:
                    fact.quality_state = "published"
                    fact.quality_policy_version = FACT_USABILITY_POLICY_VERSION
            continue
        summary.deleted += 1
        summary.deleted_by_key[fact.fact_key] = (
            summary.deleted_by_key.get(fact.fact_key, 0) + 1
        )
        if apply:
            session.delete(fact)

    if apply:
        session.commit()
    else:
        session.rollback()
    return summary


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
