from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_

from business_attributes.repository import attribute_value
from db.models import BusinessAttributeModel
from shared.utils import utcnow


UNKNOWN_TEXT_VALUES = frozenset({"", "unknown", "not_checked", "not_verified"})
DEFAULT_MINIMUM_FACT_CONFIDENCE = 85


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
        fact.confidence >= minimum_confidence,
        fact.expires_at.is_not(None),
        fact.expires_at > checked_at,
        _known_value_condition(fact),
    ]
    if require_provenance:
        conditions.append(fact.evidence_hash.is_not(None))
    return and_(*conditions)


def fact_is_eligible(
    fact: BusinessAttributeModel | None,
    *,
    minimum_confidence: int,
    now: datetime | None = None,
    require_provenance: bool = True,
) -> bool:
    """Apply the canonical eligibility policy to an already-loaded fact."""

    if fact is None:
        return False
    checked_at = now or utcnow()
    if fact.confidence < minimum_confidence:
        return False
    if require_provenance and not fact.evidence_hash:
        return False
    expires_at = fact.expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None and checked_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=checked_at.tzinfo)
    if expires_at <= checked_at:
        return False
    value = attribute_value(fact)
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
