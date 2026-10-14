from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    ValidationResultModel,
)
from shared.utils import utcnow


REQUIRED_VALIDATIONS = {
    "identity": 90,
    "business_identity": 85,
    "trade": 90,
    "location": 85,
}


def searchable_business_conditions(*, now: datetime | None = None) -> list:
    """Return the current validation conditions for a scoped business membership."""
    current_time = now or utcnow()
    conditions = [BusinessModel.status == "active"]
    for dimension, minimum_confidence in REQUIRED_VALIDATIONS.items():
        validation = aliased(
            ValidationResultModel,
            name=f"latest_{dimension}_validation",
        )
        latest_status = (
            select(validation.status)
            .where(
                validation.business_id == BusinessModel.id,
                validation.validation_type == dimension,
                validation.expires_at >= current_time,
                or_(
                    validation.niche_id.is_(None),
                    validation.niche_id == BusinessNicheMembershipModel.niche_id,
                ),
                or_(
                    validation.market_key.is_(None),
                    validation.market_key == BusinessNicheMembershipModel.market_key,
                ),
            )
            .order_by(validation.observed_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_confidence = (
            select(validation.confidence)
            .where(
                validation.business_id == BusinessModel.id,
                validation.validation_type == dimension,
                validation.expires_at >= current_time,
                or_(
                    validation.niche_id.is_(None),
                    validation.niche_id == BusinessNicheMembershipModel.niche_id,
                ),
                or_(
                    validation.market_key.is_(None),
                    validation.market_key == BusinessNicheMembershipModel.market_key,
                ),
            )
            .order_by(validation.observed_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        conditions.extend(
            [
                latest_status == "passed",
                latest_confidence >= minimum_confidence,
            ]
        )
    return conditions
