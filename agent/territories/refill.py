from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.models import LeadModel, TerritoryDeliveryModel, TerritoryModel
from job_queue.service import QueueService
from shared.utils import utcnow


def enqueue_refill_if_depleted(
    session: Session,
    territory_id: str | None,
) -> bool:
    if not territory_id:
        return False
    territory = session.get(TerritoryModel, territory_id)
    if (
        territory is None
        or territory.status != "active"
        or territory.refill_policy != "when_depleted"
    ):
        return False
    delivery = session.scalar(
        select(TerritoryDeliveryModel)
        .where(TerritoryDeliveryModel.territory_id == territory.id)
        .order_by(TerritoryDeliveryModel.created_at.desc())
        .limit(1)
    )
    if delivery is None or delivery.status not in {"ready", "partial"}:
        return False
    remaining = session.scalar(
        select(func.count())
        .select_from(LeadModel)
        .where(
            LeadModel.campaign_id == delivery.campaign_id,
            LeadModel.shortlisted_at.is_(None),
            LeadModel.last_contacted_at.is_(None),
            or_(LeadModel.review_status.is_(None), LeadModel.review_status != "not_fit"),
        )
    ) or 0
    threshold = max(1, min(5, territory.batch_size // 5))
    if remaining > threshold:
        return False
    QueueService(session).enqueue_territory_refresh(
        territory.id,
        utcnow().replace(microsecond=0).isoformat(),
        criteria_version=territory.criteria_version,
        dedupe_key=(
            f"depleted:{territory.id}:{delivery.id}:{territory.criteria_version}"
        ),
    )
    return True
