from sqlalchemy.orm import Session

from business_index.repository import BusinessIndexRepository
from job_queue.service import QueueService


def enqueue_due_business_index_refreshes(session: Session, *, limit: int = 25) -> int:
    segments = BusinessIndexRepository(session).due(limit=limit)
    queue = QueueService(session)
    for segment in segments:
        queue.enqueue_business_index_refresh(segment_id=segment.id)
    return len(segments)
