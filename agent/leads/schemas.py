from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    WORKSPACE = "workspace"
    GLOBAL = "global"


class AgentFitStatus(StrEnum):
    GOOD_FIT = "good_fit"
    MAYBE = "maybe"
    NOT_FIT = "not_fit"


class BestChannel(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    CONTACT_FORM = "contact_form"
    VISIT = "visit"
    NONE = "none"


class ApproachCopy(BaseModel):
    opener: str = Field(min_length=1, max_length=500)
    talk_track: list[str] = Field(default_factory=list, max_length=3)
    evidence_refs: list[str] = Field(default_factory=list, min_length=1, max_length=5)


class LeadApproach(ApproachCopy):
    best_channel: BestChannel
    channel_reason: str
    generated_at: datetime
    offer_updated_at: datetime


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


class QualificationScoreBreakdown(BaseModel):
    fit_score: int = Field(
        ge=0,
        le=100,
        description="ICP and problem fit only; does not include contactability.",
    )
    reachability_score: int = Field(
        ge=0,
        le=100,
        description="Contact channel quality only; does not include ICP fit.",
    )
    source_quality_score: int = Field(
        ge=0,
        le=100,
        description="Confidence that the source represents a real, relevant business entity.",
    )
    scoring_notes: list[str] = Field(default_factory=list)


class QualificationResult(BaseModel):
    qualified: bool
    fit_status: AgentFitStatus | None = None
    score: int = Field(ge=0, le=100)
    score_breakdown: QualificationScoreBreakdown | None = None
    rationale: str
    positive_signals: list[str] = Field(default_factory=list)
    signal_tags: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    criteria: list[CriterionScore] = Field(default_factory=list)
    recommended_next_step: str

    @model_validator(mode="before")
    @classmethod
    def restore_missing_explanation_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        data = dict(value)
        qualified = data.get("qualified") is True
        score = data.get("score")
        if not isinstance(data.get("rationale"), str) or not data["rationale"].strip():
            outcome = "met" if qualified else "did not meet"
            score_detail = f" with a score of {score}" if isinstance(score, int) else ""
            evidence = _first_qualification_detail(data)
            data["rationale"] = (
                f"Lead {outcome} the configured qualification threshold{score_detail}."
                + (f" {evidence}" if evidence else "")
            )
        if not isinstance(data.get("recommended_next_step"), str) or not data["recommended_next_step"].strip():
            data["recommended_next_step"] = (
                "Review the evidence before approving outreach."
                if qualified
                else "Do not send outreach."
            )
        return data


def _first_qualification_detail(value: dict[str, Any]) -> str:
    for key, prefix in (
        ("positive_signals", "Positive evidence:"),
        ("risks", "Risk:"),
        ("missing_evidence", "Missing evidence:"),
    ):
        entries = value.get(key)
        if isinstance(entries, list):
            detail = next((entry.strip() for entry in entries if isinstance(entry, str) and entry.strip()), "")
            if detail:
                return f"{prefix} {detail}"
    return ""


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
    territory_id: str | None = None
    business_id: str | None = None
    contact_id: str | None = None
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
    latest_outcome: str | None = None
    latest_outcome_at: datetime | None = None
    approach: LeadApproach | None = None
    outcome_adjustment: float = 0.0
    rank_score: float | None = None
    created_at: datetime
    updated_at: datetime
