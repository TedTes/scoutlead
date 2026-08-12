from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobType(StrEnum):
    CAMPAIGN_RUN = "campaign.run"
    MESSAGE_SEND = "message.send"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class QueueJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: JobType
    payload: dict = Field(default_factory=dict)
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
