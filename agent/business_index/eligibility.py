from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.orm import aliased

from db.models import (
    BusinessModel,
    BusinessAttributeModel,
)
from shared.utils import utcnow


def searchable_business_conditions(*, now: datetime | None = None) -> list:
    """Expose active businesses unless current evidence confirms closure.

    Niche and market fit are applied by the caller through memberships. A
    separate validation log is deliberately not part of lead eligibility.
    """
    current_time = now or utcnow()
    conditions = [BusinessModel.status == "active"]
    operational = aliased(BusinessAttributeModel, name="searchable_business_operational")
    conditions.append(
        ~exists(
            select(operational.id).where(
                operational.business_id == BusinessModel.id,
                operational.attribute_key == "business_operational",
                operational.row_type == "attribute",
                operational.value_type == "boolean",
                operational.value_boolean.is_(False),
                operational.resolution_state == "confirmed",
                operational.confidence >= 85,
                operational.source_content_hash.is_not(None),
                operational.expires_at.is_not(None),
                operational.expires_at > current_time,
            )
        )
    )
    return conditions
