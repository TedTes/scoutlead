from sqlalchemy import select
from sqlalchemy.orm import Session

from audience_runs.schemas import AudienceRunState
from db.models import AudienceRunModel
from job_queue.service import QueueService
from shared.utils import utcnow


def enqueue_waiting_audience_runs(session: Session, *, limit: int = 50) -> int:
    runs = list(
        session.scalars(
            select(AudienceRunModel)
            .where(
                AudienceRunModel.state == AudienceRunState.WAITING_VALIDATION.value,
            )
            .order_by(AudienceRunModel.deadline_at, AudienceRunModel.created_at)
            .limit(limit)
        )
    )
    queue = QueueService(session)
    for run in runs:
        queue.enqueue_audience_run(
            run.id,
            delay_seconds=0 if run.deadline_at <= utcnow() else 30,
        )
    return len(runs)
