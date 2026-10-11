from sqlalchemy import select
from sqlalchemy.orm import Session

from business_index.repository import BusinessIndexRepository
from db.models import QueueJobModel
from job_queue.schemas import JobType
from job_queue.service import QueueService


def enqueue_due_business_index_refreshes(session: Session, *, limit: int = 25) -> int:
    segments = BusinessIndexRepository(session).due(limit=limit)
    blocked_segment_ids = _segments_awaiting_admin_review(session)
    queue = QueueService(session)
    enqueued = 0
    for segment in segments:
        if segment.id in blocked_segment_ids:
            continue
        queue.enqueue_business_index_refresh(segment_id=segment.id)
        enqueued += 1
    return enqueued


def _segments_awaiting_admin_review(session: Session) -> set[str]:
    jobs = session.scalars(
        select(QueueJobModel).where(
            QueueJobModel.type == JobType.BUSINESS_INDEX_REFRESH.value
        )
    )
    terminal_review_states = {"approved", "discarded", "canceled"}
    return {
        str(job.payload.get("segment_id"))
        for job in jobs
        if job.payload.get("admin_requested")
        and job.payload.get("processing_mode") == "review_first"
        and job.payload.get("review_state", "pending") not in terminal_review_states
    }
