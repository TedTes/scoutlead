from sqlalchemy.orm import Session

from job_queue.repository import QueueRepository
from job_queue.schemas import JobType


class QueueService:
    def __init__(self, session: Session) -> None:
        self.queue = QueueRepository(session)

    def enqueue_campaign_run(self, campaign_id: str):
        return self.queue.enqueue(JobType.CAMPAIGN_RUN, {"campaign_id": campaign_id})

    def enqueue_message_send(self, message_id: str):
        return self.queue.enqueue(JobType.MESSAGE_SEND, {"message_id": message_id})

    def enqueue_territory_refresh(self, territory_id: str, scheduled_date: str):
        key = f"{territory_id}:{scheduled_date}"
        return self.queue.enqueue_once(
            JobType.TERRITORY_REFRESH,
            {"territory_id": territory_id, "scheduled_date": scheduled_date},
            dedupe_key=key,
            max_attempts=2,
        )

    def enqueue_business_index_refresh(
        self,
        *,
        segment_id: str,
        campaign_id: str | None = None,
        requested_deficit: int = 0,
        commit: bool = True,
    ):
        return self.queue.enqueue_once(
            JobType.BUSINESS_INDEX_REFRESH,
            {
                "segment_id": segment_id,
                "campaign_id": campaign_id,
                "requested_deficit": max(0, requested_deficit),
            },
            dedupe_key=segment_id,
            max_attempts=3,
            commit=commit,
        )
