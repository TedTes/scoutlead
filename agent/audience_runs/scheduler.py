from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import TerritoryModel
from job_queue.service import QueueService


def enqueue_waiting_audience_runs(session: Session, *, limit: int = 50) -> int:
    """Queue saved searches that are waiting for database-only matching."""
    audiences = list(
        session.scalars(
            select(TerritoryModel)
            .where(TerritoryModel.match_state == "queued")
            .order_by(TerritoryModel.updated_at)
            .limit(limit)
        )
    )
    queue = QueueService(session)
    for audience in audiences:
        queue.enqueue_audience_run(audience.id, commit=False)
    if audiences:
        session.commit()
    return len(audiences)
