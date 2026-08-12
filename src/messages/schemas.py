from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from campaigns.schemas import OutreachChannel


class MessageStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    REPLIED = "replied"
    CANCELLED = "cancelled"


class OutreachDraft(BaseModel):
    channel: OutreachChannel = OutreachChannel.EMAIL
    subject: str | None = None
    body: str = Field(min_length=1)
    personalization_notes: list[str] = Field(default_factory=list)
    approach_tag: str = "default"


class MessageApproval(BaseModel):
    approved_by: str = Field(min_length=1)
    notes: str | None = None


class MessageUpdate(BaseModel):
    subject: str | None = None
    body: str | None = Field(default=None, min_length=1)
    personalization_notes: list[str] | None = None
    approach_tag: str | None = None


class MessageRead(OutreachDraft):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    product_id: str
    lead_id: str
    status: MessageStatus
    approval: dict | None = None
    sent_at: datetime | None = None
    provider_message_id: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
