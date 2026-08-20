from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LeadStatus(StrEnum):
    DISCOVERED = "discovered"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    OUTREACH_DRAFTED = "outreach_drafted"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SENT = "sent"
    RESPONDED = "responded"
    ARCHIVED = "archived"


class LeadFitType(StrEnum):
    TARGET_CUSTOMER = "target_customer"
    COMPETITOR_OR_ALTERNATIVE = "competitor_or_alternative"
    VENDOR_TO_TARGET_CUSTOMER = "vendor_to_target_customer"
    CONTENT_OR_DIRECTORY = "content_or_directory"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


class LeadResearch(BaseModel):
    summary: str
    lead_type: LeadFitType = LeadFitType.UNKNOWN
    business_type: str | None = None
    geography: str | None = None
    website_url: str | None = None
    contact_email: str | None = None
    contact_name: str | None = None
    contact_candidates: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    pain_indicators: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)


class CriterionScore(BaseModel):
    criterion_id: str
    label: str
    score: int = Field(ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class QualificationResult(BaseModel):
    qualified: bool
    score: int = Field(ge=0, le=100)
    rationale: str
    criteria: list[CriterionScore] = Field(default_factory=list)
    recommended_next_step: str


class LeadCreate(BaseModel):
    campaign_id: str
    product_id: str
    company_name: str = Field(min_length=1)
    website_url: str | None = None
    contact_email: str | None = None
    geography: str | None = None
    description: str | None = None
    source: str = "manual"
    raw_sources: list[dict] = Field(default_factory=list)


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: LeadStatus
    research: LeadResearch | None = None
    qualification: QualificationResult | None = None
    created_at: datetime
    updated_at: datetime
