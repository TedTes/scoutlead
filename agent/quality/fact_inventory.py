from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.repository import fact_value
from db.models import (
    BusinessFactModel,
    FactClaimModel,
    SignalDefinitionModel,
    SourceObservationModel,
    ValidationResultModel,
)
from shared.utils import utcnow
from signal_validation.service import COLLECTOR_SOURCES


UNKNOWN_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})


@dataclass
class FactInventorySummary:
    dry_run: bool
    checked: int = 0
    healthy: int = 0
    repaired_definition_links: int = 0
    staged: int = 0
    rejected: int = 0
    issues: dict[str, int] = field(default_factory=dict)
    details: list[dict[str, Any]] = field(default_factory=list)


def audit_fact_inventory(
    session: Session,
    *,
    apply: bool = False,
    limit: int = 25000,
    include_details: bool = False,
) -> FactInventorySummary:
    """Audit canonical facts and optionally apply conservative state repairs.

    This never invents values or publishes facts. Apply mode repairs an
    unambiguous signal-definition link, then stages/rejects unsafe rows so the
    normal collection and validation jobs can rebuild them.
    """

    now = utcnow()
    definitions = list(session.scalars(select(SignalDefinitionModel)))
    definitions_by_key = {definition.key: definition for definition in definitions}
    facts = list(
        session.scalars(
            select(BusinessFactModel).order_by(BusinessFactModel.id).limit(limit)
        )
    )
    summary = FactInventorySummary(dry_run=not apply)
    issue_counts: dict[str, int] = {}
    for fact in facts:
        summary.checked += 1
        issues: list[str] = []
        definition = definitions_by_key.get(fact.fact_key)
        if definition is None:
            issues.append("missing_signal_definition")
        elif fact.signal_definition_id != definition.id:
            issues.append("definition_link_mismatch")

        observation = (
            session.get(SourceObservationModel, fact.source_observation_id)
            if fact.source_observation_id
            else None
        )
        if observation is None:
            issues.append("missing_source_observation")
        elif definition is not None:
            expected_sources = COLLECTOR_SOURCES.get(definition.collector_key or "")
            if expected_sources and observation.source not in expected_sources:
                issues.append("source_contract_mismatch")

        value = fact_value(fact)
        if value is None or (
            isinstance(value, str) and value.strip().lower() in UNKNOWN_VALUES
        ):
            issues.append("unknown_value")
        if fact.expires_at is None or _aware(fact.expires_at) <= _aware(now):
            issues.append("expired_or_unbounded")

        newest_claim = session.scalar(
            select(FactClaimModel)
            .where(
                FactClaimModel.business_id == fact.business_id,
                FactClaimModel.fact_key == fact.fact_key,
            )
            .order_by(
                FactClaimModel.observed_at.desc(),
                FactClaimModel.confidence.desc(),
            )
            .limit(1)
        )
        if newest_claim is None:
            issues.append("missing_claim")
        elif (
            newest_claim.source_observation_id != fact.source_observation_id
            or not _values_equal(newest_claim.value, value)
        ):
            issues.append("resolved_fact_claim_mismatch")

        latest_validation = session.scalar(
            select(ValidationResultModel)
            .where(
                ValidationResultModel.business_id == fact.business_id,
                ValidationResultModel.validation_type == f"signal:{fact.fact_key}",
            )
            .order_by(
                ValidationResultModel.observed_at.desc(),
                ValidationResultModel.created_at.desc(),
                ValidationResultModel.id.desc(),
            )
            .limit(1)
        )
        passed_validation = bool(
            latest_validation is not None
            and latest_validation.status == "passed"
            and latest_validation.source_observation_id
            == fact.source_observation_id
            and _aware(latest_validation.expires_at) > _aware(now)
        )
        if not passed_validation:
            issues.append("missing_current_validation")

        issues = list(dict.fromkeys(issues))
        if not issues:
            summary.healthy += 1
            continue
        for issue in issues:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
        if include_details:
            summary.details.append(
                {
                    "fact_id": fact.id,
                    "business_id": fact.business_id,
                    "fact_key": fact.fact_key,
                    "issues": issues,
                }
            )
        if not apply:
            continue
        if definition is not None and fact.signal_definition_id != definition.id:
            fact.signal_definition_id = definition.id
            summary.repaired_definition_links += 1
        hard_failure = any(
            issue
            in {
                "missing_signal_definition",
                "missing_source_observation",
                "source_contract_mismatch",
                "unknown_value",
            }
            for issue in issues
        )
        fact.quality_state = "rejected" if hard_failure else "staged"
        if "expired_or_unbounded" in issues:
            fact.resolution_state = "stale"
        elif "resolved_fact_claim_mismatch" in issues:
            fact.resolution_state = "conflicted"
        elif hard_failure:
            fact.resolution_state = "unknown"
        if hard_failure:
            fact.confidence = 0
            summary.rejected += 1
        else:
            summary.staged += 1

    summary.issues = dict(sorted(issue_counts.items()))
    if apply:
        session.commit()
    return summary


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-6
    return left == right


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
