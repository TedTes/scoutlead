from datetime import datetime
from enum import StrEnum
from typing import Any

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


class LeadReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    GOOD_FIT = "good_fit"
    MAYBE = "maybe"
    NOT_FIT = "not_fit"


class ContactVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VALID = "valid"
    RISKY = "risky"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class ContactPolicyStatus(StrEnum):
    ALLOWED = "allowed"
    SUPPRESSED = "suppressed"
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"


class SuppressionScope(StrEnum):
    PRODUCT = "product"
    GLOBAL = "global"


class AgentFitStatus(StrEnum):
    GOOD_FIT = "good_fit"
    MAYBE = "maybe"
    NOT_FIT = "not_fit"


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
    fit_status: AgentFitStatus | None = None
    score: int = Field(ge=0, le=100)
    rationale: str
    positive_signals: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
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


class LeadUpdate(BaseModel):
    review_status: LeadReviewStatus | None = None
    review_note: str | None = None
    shortlisted: bool | None = None


class LeadContactPolicyUpdate(BaseModel):
    status: ContactPolicyStatus
    reason: str | None = None
    scope: SuppressionScope = SuppressionScope.PRODUCT


class LeadVerification(BaseModel):
    status: ContactVerificationStatus
    provider: str
    reason: str | None = None
    score: int = Field(ge=0, le=100)
    details: dict[str, Any] = Field(default_factory=dict)


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: LeadStatus
    review_status: LeadReviewStatus = LeadReviewStatus.UNREVIEWED
    review_note: str | None = None
    reviewed_at: datetime | None = None
    shortlisted_at: datetime | None = None
    contact_policy_status: ContactPolicyStatus = ContactPolicyStatus.ALLOWED
    contact_policy_reason: str | None = None
    contact_policy_checked_at: datetime | None = None
    last_contacted_at: datetime | None = None
    verification_status: ContactVerificationStatus = ContactVerificationStatus.UNVERIFIED
    verification_provider: str | None = None
    verification_checked_at: datetime | None = None
    verification_reason: str | None = None
    verification_score: int | None = None
    verification_details: dict[str, Any] | None = None
    research: LeadResearch | None = None
    qualification: QualificationResult | None = None
    created_at: datetime
    updated_at: datetime
