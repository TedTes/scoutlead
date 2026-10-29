from __future__ import annotations

from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_facts.eligibility import fact_is_eligible
from business_facts.freshness import fact_is_current
from business_facts.repository import fact_value
from db.models import BusinessFactModel, SignalDefinitionModel, ValidationResultModel
from shared.utils import utcnow


def enforce_fact_publication_invariants(
    session: Session,
    *,
    commit: bool = True,
) -> dict[str, int]:
    """Demote facts that no longer satisfy the public evidence contract."""

    now = utcnow()
    definitions = {
        definition.id: definition
        for definition in session.scalars(select(SignalDefinitionModel))
    }
    summary = {
        "checked": 0,
        "demoted": 0,
        "expired": 0,
        "unknown": 0,
        "unconfirmed": 0,
        "low_confidence": 0,
        "missing_provenance": 0,
        "missing_validation": 0,
    }
    facts = list(
        session.scalars(
            select(BusinessFactModel).where(
                BusinessFactModel.quality_state == "published"
            )
        )
    )
    for fact in facts:
        summary["checked"] += 1
        definition = definitions.get(fact.signal_definition_id or "")
        minimum_confidence = int(
            ((definition.config or {}) if definition is not None else {}).get(
                "minimum_confidence",
                90,
            )
        )
        fact_eligible = fact_is_eligible(
            fact,
            minimum_confidence=minimum_confidence,
            now=now,
            require_provenance=True,
        )
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
            and latest_validation.confidence >= minimum_confidence
            and _aware(latest_validation.expires_at) > _aware(now)
            and latest_validation.source_observation_id
            == fact.source_observation_id
        )
        if fact_eligible and passed_validation:
            continue
        summary["demoted"] += 1
        value = fact_value(fact)
        if not fact_is_current(expires_at=fact.expires_at, now=now):
            summary["expired"] += 1
            fact.resolution_state = "stale"
        elif value is None or (
            isinstance(value, str)
            and value.strip().lower() in {"", "unknown", "not_checked", "not_verified"}
        ):
            summary["unknown"] += 1
            fact.resolution_state = "unknown"
        elif fact.resolution_state != "confirmed":
            summary["unconfirmed"] += 1
        elif fact.confidence < minimum_confidence:
            summary["low_confidence"] += 1
        elif fact.source_observation_id is None:
            summary["missing_provenance"] += 1
        elif not passed_validation:
            summary["missing_validation"] += 1
        fact.quality_state = "staged"
    if commit:
        session.commit()
    else:
        session.flush()
    return summary


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
