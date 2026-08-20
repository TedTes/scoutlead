from datetime import datetime
from enum import StrEnum
from typing import Any

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


class CampaignGoalType(StrEnum):
    LEARN = "learn"
    SELL = "sell"


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
    name: str = Field(min_length=1)
    goal_type: CampaignGoalType = CampaignGoalType.LEARN
    icp_preset_id: str | None = None
    source_preset_id: str | None = None
    source_input: str | None = None
    source_inputs: dict[str, Any] = Field(default_factory=dict)
    max_leads: int = Field(gt=0, le=1000)
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
    contacted_lead_count: int = 0
    verified_lead_count: int = 0
    signaled_lead_count: int = 0
    qualified_lead_count: int
    drafted_message_count: int


class CampaignPreflightCheck(BaseModel):
    name: str
    status: str
    detail: str
    required: bool = True


class CampaignPreflightRead(BaseModel):
    campaign_id: str
    ready: bool
    checks: list[CampaignPreflightCheck]
