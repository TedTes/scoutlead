from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import TerritoryModel
from job_queue.service import QueueService
from shared.utils import utcnow


def enqueue_due_territories(session: Session, *, now: datetime | None = None) -> int:
    now = now or utcnow()
    territories = list(
        session.scalars(
            select(TerritoryModel).where(
                TerritoryModel.status == "active",
                TerritoryModel.next_run_at.is_not(None),
                TerritoryModel.next_run_at <= now,
            )
        )
    )
    queue = QueueService(session)
    for territory in territories:
        scheduled = _aware(territory.next_run_at or now)
        queue.enqueue_territory_refresh(
            territory.id,
            scheduled.replace(microsecond=0).isoformat(),
            criteria_version=territory.criteria_version,
        )
    return len(territories)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
