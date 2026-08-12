from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    DISCOVERING = "discovering"
    RESEARCHING = "researching"
    QUALIFYING = "qualifying"
    DRAFTING_OUTREACH = "drafting_outreach"
    AWAITING_APPROVAL = "awaiting_approval"
    SENDING = "sending"
    TRACKING = "tracking"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


class CampaignStage(StrEnum):
    DISCOVERY = "discovery"
    RESEARCH = "research"
    QUALIFICATION = "qualification"
    OUTREACH = "outreach"
    RESPONSE = "response"
    COMPLETE = "complete"


class OutreachChannel(StrEnum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    PHONE = "phone"
    MANUAL = "manual"


class LeadSeedInput(BaseModel):
    company_name: str = Field(min_length=1)
    website_url: str | None = None
    contact_email: str | None = None
    geography: str | None = None
    description: str | None = None
    source: str | None = None
    raw: dict | None = None


class CampaignCreate(BaseModel):
    product_id: str = Field(min_length=1)
    name: str | None = None
    max_leads: int = Field(default=25, gt=0, le=1000)
    channels: list[OutreachChannel] = Field(default_factory=lambda: [OutreachChannel.EMAIL])
    discovery_seeds: list[LeadSeedInput] = Field(default_factory=list)
    goal_override: str | None = None


class CampaignRead(CampaignCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: CampaignStatus
    stage: CampaignStage
    failure_reason: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CampaignRunSummary(BaseModel):
    campaign: CampaignRead
    discovered_lead_count: int
    researched_lead_count: int
    qualified_lead_count: int
    drafted_message_count: int
