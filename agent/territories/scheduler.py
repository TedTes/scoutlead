from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from audience_runs.service import AudienceRunService
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
        run = AudienceRunService(
            session,
            workspace_id=territory.workspace_id,
        ).create(
            territory.id,
            commit=False,
        )
        queue.enqueue_audience_run(run.id, commit=False)
        interval_days = {
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
        }.get(territory.refill_policy)
        territory.next_run_at = (
            now + timedelta(days=interval_days)
            if interval_days is not None
            else None
        )
    session.commit()
    return len(territories)
