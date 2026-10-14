from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobType(StrEnum):
    MESSAGE_SEND = "message.send"
    AUDIENCE_RUN = "audience.run"
    BUSINESS_INDEX_REFRESH = "business_index.refresh"
    SOURCE_FETCH = "source.fetch"
    BUSINESS_IDENTITY_RESOLVE = "business.identity_resolve"
    BUSINESS_OPPORTUNITY_AUDIT = "business.opportunity_audit"
    BUSINESS_SEARCH_EVALUATE = "business.search_evaluate"
    BUSINESS_SEARCH_EVALUATE_BATCH = "business.search_evaluate_batch"
    SIGNAL_COLLECTION = "signal.collection"
    SIGNAL_VALIDATION = "signal.validation"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELED = "canceled"


class QueueJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: JobType
    payload: dict = Field(default_factory=dict)
    status: JobStatus
    attempts: int
    max_attempts: int
    run_after: datetime
    idempotency_key: str | None = None
    parent_run_id: str | None = None
    locked_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    last_error: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
