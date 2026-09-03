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
