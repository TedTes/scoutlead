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


class CampaignOutreachAudience(StrEnum):
    SELECTED = "selected"
    READY_CONTACTS = "ready_contacts"
    READY_SHORTLIST = "ready_shortlist"


class CampaignOutreachDraftCreate(BaseModel):
    audience: CampaignOutreachAudience = CampaignOutreachAudience.READY_CONTACTS
    lead_ids: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    approach_tag: str = Field(default="campaign_template", min_length=1, max_length=255)


class MessageApproval(BaseModel):
    approved_by: str = Field(min_length=1)
    notes: str | None = None


class CampaignMessageApproval(BaseModel):
    message_ids: list[str] = Field(default_factory=list)
    approved_by: str = Field(min_length=1)
    notes: str | None = None


class CampaignMessageSend(BaseModel):
    message_ids: list[str] = Field(default_factory=list)


class MessageUpdate(BaseModel):
    subject: str | None = None
    body: str | None = Field(default=None, min_length=1)
    personalization_notes: list[str] | None = None
    approach_tag: str | None = None


class MessageReplyMark(BaseModel):
    body: str | None = None


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


class CampaignMessageSkip(BaseModel):
    lead_id: str | None = None
    message_id: str | None = None
    company_name: str | None = None
    reason: str


class CampaignMessageBatchResult(BaseModel):
    messages: list[MessageRead] = Field(default_factory=list)
    skipped: list[CampaignMessageSkip] = Field(default_factory=list)
    created_count: int = 0
    reused_count: int = 0
    approved_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
