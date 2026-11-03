from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import aliased

from db.models import (
    BusinessModel,
    BusinessFactModel,
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
    """Require scoped validation and exclude confirmed closed businesses."""
    current_time = now or utcnow()
    conditions = [BusinessModel.status == "active"]
    operational = aliased(BusinessFactModel, name="searchable_business_operational")
    conditions.append(
        ~exists(
            select(operational.id).where(
                operational.business_id == BusinessModel.id,
                operational.fact_key == "business_operational",
                operational.value_type == "boolean",
                operational.value_boolean.is_(False),
                operational.quality_state == "published",
                operational.resolution_state == "confirmed",
                operational.confidence >= 85,
                operational.source_observation_id.is_not(None),
                operational.expires_at.is_not(None),
                operational.expires_at > current_time,
            )
        )
    )
    for dimension, minimum_confidence in REQUIRED_VALIDATIONS.items():
        validation = aliased(
            ValidationResultModel,
            name=f"latest_{dimension}_validation",
        )
        scoped = (
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
        latest_status = (
            select(validation.status)
            .where(*scoped)
            .order_by(validation.observed_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        latest_confidence = (
            select(validation.confidence)
            .where(*scoped)
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
