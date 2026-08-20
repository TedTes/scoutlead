from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ObservationType(StrEnum):
    LEAD_QUALITY = "lead_quality"
    OUTREACH_VARIANT = "outreach_variant"
    RESPONSE = "response"
    CAMPAIGN_SUMMARY = "campaign_summary"
    MANUAL_NOTE = "manual_note"
    TOOL_HIT_RATE = "tool_hit_rate"


class CampaignMemoryCreate(BaseModel):
    product_id: str
    campaign_id: str
    type: ObservationType
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    score_impact: float | None = None


class CampaignMemoryRead(CampaignMemoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class LearningSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    campaign_id: str | None = None
    summary: str
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class RelevantMemory(BaseModel):
    observations: list[CampaignMemoryRead] = Field(default_factory=list)
    summaries: list[LearningSummaryRead] = Field(default_factory=list)
