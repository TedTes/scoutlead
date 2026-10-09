from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from leads.schemas import LeadReviewStatus


class AudienceRunState(StrEnum):
    QUEUED = "queued"
    MATCHING = "matching"
    EXPANDING = "expanding"
    WAITING_VALIDATION = "waiting_validation"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class AudienceResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    audience_id: str
    business_id: str
    publication_id: str
    rank_position: int
    is_new: bool
    match_snapshot: dict
    review_status: LeadReviewStatus
    review_note: str | None = None
    reviewed_at: datetime | None = None
    shortlisted_at: datetime | None = None
    contacted_at: datetime | None = None
    outreach_lead_id: str | None = None
    created_at: datetime
    updated_at: datetime


class AudienceResultUpdate(BaseModel):
    review_status: LeadReviewStatus | None = None
    review_note: str | None = None
    shortlisted: bool | None = None


class AudienceLeadRead(BaseModel):
    """Lead-shaped audience match used by the existing review UI."""

    id: str
    campaign_id: str
    territory_id: str
    product_id: str
    business_id: str
    outreach_lead_id: str | None = None
    contact_id: str | None = None
    company_name: str
    website_url: str | None = None
    contact_email: str | None = None
    geography: str | None = None
    description: str | None = None
    source: str
    raw_sources: list[dict] = Field(default_factory=list)
    status: str = "qualified"
    review_status: LeadReviewStatus = LeadReviewStatus.UNREVIEWED
    review_note: str | None = None
    reviewed_at: datetime | None = None
    shortlisted_at: datetime | None = None
    contact_policy_status: str = "allowed"
    contact_policy_reason: str | None = None
    contact_policy_checked_at: datetime | None = None
    last_contacted_at: datetime | None = None
    verification_status: str = "unverified"
    verification_provider: str | None = None
    verification_checked_at: datetime | None = None
    verification_reason: str | None = None
    verification_score: int | None = None
    verification_details: dict | None = None
    research: dict | None = None
    qualification: dict | None = None
    latest_outcome: str | None = None
    latest_outcome_at: datetime | None = None
    approach: dict | None = None
    outcome_adjustment: float = 0.0
    rank_score: float | None = None
    created_at: datetime
    updated_at: datetime


class AudienceRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    audience_id: str
    criteria_version: int
    state: AudienceRunState
    requested_count: int
    result_count: int
    new_result_count: int
    index_snapshot_at: datetime | None = None
    deadline_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    outreach_campaign_id: str | None = None
    results: list[AudienceResultRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
