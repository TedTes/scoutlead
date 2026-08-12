from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ResponseIntent(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    QUESTION = "question"
    INTERVIEW_REQUEST = "interview_request"
    PRODUCT_TRIAL_INTEREST = "product_trial_interest"
    OUT_OF_OFFICE = "out_of_office"
    UNKNOWN = "unknown"


class FollowUpAction(StrEnum):
    REPLY = "reply"
    SCHEDULE_INTERVIEW = "schedule_interview"
    SEND_TRIAL_INFO = "send_trial_info"
    CLOSE = "close"
    WAIT = "wait"
    MANUAL_REVIEW = "manual_review"


class ConversationStatus(StrEnum):
    OPEN = "open"
    WAITING = "waiting"
    INTERESTED = "interested"
    CLOSED = "closed"
    MANUAL_REVIEW = "manual_review"


class EventDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    INTERNAL = "internal"


class ResponseClassification(BaseModel):
    intent: ResponseIntent
    confidence: int = Field(ge=0, le=100)
    rationale: str
    suggested_reply: str | None = None
    follow_up_action: FollowUpAction


class ConversationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    direction: EventDirection
    message_id: str | None = None
    body: str
    classification: ResponseClassification | None = None
    created_at: datetime


class InboundResponseCreate(BaseModel):
    body: str = Field(min_length=1)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    product_id: str
    lead_id: str
    status: ConversationStatus
    events: list[ConversationEventRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
