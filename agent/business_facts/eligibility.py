from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, exists, func, literal, or_, select
from sqlalchemy.orm import aliased

from business_facts.repository import fact_value
from db.models import BusinessFactModel, ValidationResultModel
from shared.utils import utcnow


UNKNOWN_TEXT_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})


def eligible_fact_condition(
    fact,
    *,
    minimum_confidence: int,
    now: datetime | None = None,
    require_provenance: bool = True,
    require_validation: bool = False,
):
    """Return the one SQL predicate used to expose canonical facts to consumers."""

    checked_at = now or utcnow()
    conditions = [
        fact.quality_state == "published",
        fact.resolution_state == "confirmed",
        fact.confidence >= minimum_confidence,
        fact.expires_at.is_not(None),
        fact.expires_at > checked_at,
        _known_value_condition(fact),
    ]
    if require_provenance:
        conditions.append(fact.source_observation_id.is_not(None))
    if require_validation:
        passed = aliased(ValidationResultModel)
        newer = aliased(ValidationResultModel)
        newer_validation_exists = exists(
            select(newer.id).where(
                newer.business_id == passed.business_id,
                newer.validation_type == passed.validation_type,
                or_(
                    newer.observed_at > passed.observed_at,
                    and_(
                        newer.observed_at == passed.observed_at,
                        newer.created_at > passed.created_at,
                    ),
                    and_(
                        newer.observed_at == passed.observed_at,
                        newer.created_at == passed.created_at,
                        newer.id > passed.id,
                    ),
                ),
            )
        )
        conditions.append(
            exists(
                select(passed.id).where(
                    passed.business_id == fact.business_id,
                    passed.validation_type == literal("signal:") + fact.fact_key,
                    passed.status == "passed",
                    passed.confidence >= minimum_confidence,
                    passed.expires_at > checked_at,
                    passed.source_observation_id == fact.source_observation_id,
                    ~newer_validation_exists,
                )
            )
        )
    return and_(*conditions)


def fact_is_eligible(
    fact: BusinessFactModel | None,
    *,
    minimum_confidence: int,
    now: datetime | None = None,
    require_provenance: bool = True,
) -> bool:
    """Apply the canonical eligibility policy to an already-loaded fact."""

    if fact is None:
        return False
    checked_at = now or utcnow()
    if fact.quality_state != "published" or fact.resolution_state != "confirmed":
        return False
    if fact.confidence < minimum_confidence:
        return False
    if require_provenance and fact.source_observation_id is None:
        return False
    expires_at = fact.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None and checked_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=checked_at.tzinfo)
    if expires_at <= checked_at:
        return False
    value = fact_value(fact)
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in UNKNOWN_TEXT_VALUES:
        return False
    return True


def _known_value_condition(fact):
    normalized_text = func.lower(func.trim(fact.value_text))
    return or_(
        and_(fact.value_type == "boolean", fact.value_boolean.is_not(None)),
        and_(fact.value_type == "number", fact.value_number.is_not(None)),
        and_(
            fact.value_type == "text",
            fact.value_text.is_not(None),
            normalized_text.not_in(tuple(UNKNOWN_TEXT_VALUES)),
        ),
    )
