from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IcpVerdictValue(StrEnum):
    STRONG = "strong"
    MIXED = "mixed"
    WEAK = "weak"
    INVALID = "invalid"
    INSUFFICIENT_DATA = "insufficient_data"


class Finding(BaseModel):
    theme: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)
    confidence: int = Field(default=0, ge=0, le=100)


class IcpVerdict(BaseModel):
    verdict: IcpVerdictValue
    rationale: str
    recommended_action: str


class CampaignInsightDraft(BaseModel):
    summary: str
    findings: list[Finding] = Field(default_factory=list)
    icp_verdict: IcpVerdict
    evidence: list[str] = Field(default_factory=list)


class CampaignInsightRead(CampaignInsightDraft):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    product_id: str
    goal_type: str
    metrics_snapshot: dict
    created_at: datetime
    updated_at: datetime
