from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from shared.utils import utcnow
from signal_validation.service import COLLECTOR_SOURCES
from source_observations.integrity import evaluate_observation_integrity


UNKNOWN_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})


@dataclass
class FactRepairSummary:
    dry_run: bool
    checked: int = 0
    unchanged: int = 0
    repaired: int = 0
    repaired_values: int = 0
    repaired_source_links: int = 0
    repaired_claim_links: int = 0
    repaired_definition_links: int = 0
    conflicted: int = 0
    deleted_irrecoverable: int = 0
    unresolved: int = 0
    actions: dict[str, int] = field(default_factory=dict)
    details: list[dict[str, Any]] = field(default_factory=list)


def repair_current_facts(
    session: Session,
    *,
    apply: bool = False,
    limit: int = 25000,
    include_details: bool = False,
) -> FactRepairSummary:
    """Rebuild current facts from intact, current claims without inventing evidence.

    Claims and source observations are never changed or deleted. A current fact is
    deleted only when its value is unknown or its observation is missing and no
    intact, current claim can reconstruct it.
    """

    now = utcnow()
    definitions = list(session.scalars(select(SignalDefinitionModel)))
    definitions_by_key = {row.key: row for row in definitions}
    facts = list(
        session.scalars(
            select(BusinessFactModel).order_by(BusinessFactModel.id).limit(limit)
        )
    )
    summary = FactRepairSummary(dry_run=not apply)
    if not facts:
        return summary

    business_ids = {fact.business_id for fact in facts}
    claims = list(
        session.scalars(
            select(FactClaimModel)
            .where(FactClaimModel.business_id.in_(business_ids))
            .order_by(
                FactClaimModel.observed_at.desc(),
                FactClaimModel.confidence.desc(),
                FactClaimModel.id.desc(),
            )
        )
    )
    claims_by_key: dict[tuple[str, str], list[FactClaimModel]] = {}
    for claim in claims:
        claims_by_key.setdefault((claim.business_id, claim.fact_key), []).append(claim)

    observation_ids = {
        observation_id
        for observation_id in [
            *(fact.source_observation_id for fact in facts),
            *(claim.source_observation_id for claim in claims),
        ]
        if observation_id
    }
    observations = {
        row.id: row
        for row in session.scalars(
            select(SourceObservationModel).where(
                SourceObservationModel.id.in_(observation_ids)
            )
        )
    }

    for fact in facts:
        summary.checked += 1
        definition = definitions_by_key.get(fact.fact_key)
        current_value = fact_value(fact)
        expected_sources = (
            COLLECTOR_SOURCES.get(definition.collector_key or "")
            if definition is not None
            else None
        )
        valid_claims: list[FactClaimModel] = []
        for claim in claims_by_key.get((fact.business_id, fact.fact_key), []):
            if _is_unknown(claim.value) or _aware(claim.expires_at) <= _aware(now):
                continue
            observation = observations.get(claim.source_observation_id)
            integrity = evaluate_observation_integrity(
                observation,
                expected_business_id=fact.business_id,
                expected_sources=expected_sources,
                now=now,
            )
            if integrity.status == "passed":
                valid_claims.append(claim)

        chosen = valid_claims[0] if valid_claims else None

        current_observation = observations.get(fact.source_observation_id or "")
        irrecoverable = chosen is None and (
            _is_unknown(current_value) or current_observation is None
        )
        if irrecoverable:
            _count(summary, "delete_irrecoverable")
            summary.deleted_irrecoverable += 1
            _detail(
                summary,
                include_details,
                fact,
                "delete_irrecoverable",
                "Unknown value or missing observation with no intact current claim.",
            )
            if apply:
                session.delete(fact)
            continue

        if chosen is None:
            summary.unresolved += 1
            _count(summary, "leave_unresolved")
            _detail(
                summary,
                include_details,
                fact,
                "leave_unresolved",
                "No intact current claim can safely rebuild this fact.",
            )
            continue

        chosen_value = chosen.value
        supporting = [
            claim.id for claim in valid_claims if _values_equal(claim.value, chosen_value)
        ]
        conflicting = any(
            not _values_equal(claim.value, chosen_value) and claim.confidence >= 90
            for claim in valid_claims
        )
        changes: list[str] = []
        if definition is not None and fact.signal_definition_id != definition.id:
            changes.append("definition")
            summary.repaired_definition_links += 1
        if not _values_equal(current_value, chosen_value):
            changes.append("value")
            summary.repaired_values += 1
        if fact.source_observation_id != chosen.source_observation_id:
            changes.append("source")
            summary.repaired_source_links += 1
        if set(fact.supporting_claim_ids or []) != set(supporting):
            changes.append("claims")
            summary.repaired_claim_links += 1

        target_resolution = "conflicted" if conflicting else "confirmed"
        timing_changed = (
            _aware(fact.observed_at) != _aware(chosen.observed_at)
            or _aware_optional(fact.expires_at) != _aware_optional(chosen.expires_at)
        )
        if timing_changed:
            changes.append("timing")
        # Confidence, resolution, and quality are validator-owned after the
        # evidence links are repaired. Differences in those fields alone must
        # not restage a fact that validation has already accepted or rejected.
        if not changes:
            summary.unchanged += 1
            continue

        summary.repaired += 1
        if conflicting:
            summary.conflicted += 1
        _count(summary, "repair_from_claim")
        _detail(
            summary,
            include_details,
            fact,
            "repair_from_claim",
            ", ".join(changes or ["metadata"]),
            extra={
                "current_value": current_value,
                "chosen_value": chosen_value,
                "current_source_observation_id": fact.source_observation_id,
                "chosen_source_observation_id": chosen.source_observation_id,
                "chosen_claim_id": chosen.id,
                "chosen_claim_confidence": chosen.confidence,
                "conflicting": conflicting,
            },
        )
        if not apply:
            continue
        _set_value(fact, chosen_value)
        fact.signal_definition_id = definition.id if definition is not None else None
        fact.source_observation_id = chosen.source_observation_id
        fact.supporting_claim_ids = supporting
        fact.confidence = chosen.confidence
        fact.observed_at = chosen.observed_at
        fact.expires_at = chosen.expires_at
        fact.resolution_state = target_resolution
        fact.quality_state = "staged"
        fact.resolver_version = max(fact.resolver_version, 2)

    if apply:
        session.commit()
    return summary


def _set_value(fact: BusinessFactModel, value: Any) -> None:
    fact.value_text = None
    fact.value_number = None
    fact.value_boolean = None
    if isinstance(value, bool):
        fact.value_type = "boolean"
        fact.value_boolean = value
    elif isinstance(value, (int, float)):
        fact.value_type = "number"
        fact.value_number = float(value)
    else:
        fact.value_type = "text"
        fact.value_text = str(value)


def _is_unknown(value: Any) -> bool:
    return value is None or (
        isinstance(value, str) and value.strip().lower() in UNKNOWN_VALUES
    )


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _aware_optional(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None


def _count(summary: FactRepairSummary, key: str) -> None:
    summary.actions[key] = summary.actions.get(key, 0) + 1


def _detail(
    summary: FactRepairSummary,
    enabled: bool,
    fact: BusinessFactModel,
    action: str,
    reason: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    if enabled:
        summary.details.append(
            {
                "fact_id": fact.id,
                "business_id": fact.business_id,
                "fact_key": fact.fact_key,
                "action": action,
                "reason": reason,
                **(extra or {}),
            }
        )
