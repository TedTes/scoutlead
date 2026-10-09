from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceItemState(StrEnum):
    FETCHED = "fetched"
    NEEDS_REVIEW = "needs_review"
    RELEVANT = "relevant"
    REJECTED = "rejected"
    IDENTITY_RESOLVED = "identity_resolved"
    VALIDATING = "validating"
    VALIDATED = "validated"
    AUDIT_PENDING = "audit_pending"
    AUDITED = "audited"
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    FAILED = "failed"


class SourceItemStage(StrEnum):
    RELEVANCE = "relevance"
    IDENTITY = "identity"
    VALIDATION = "validation"
    OPPORTUNITY = "opportunity"
    ELIGIBILITY = "eligibility"


class SourceItemDecisionValue(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    DUPLICATE = "duplicate"
    RESOLVED = "resolved"
    VALIDATED = "validated"
    AUDITED = "audited"
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"
    FAILED = "failed"


class SourceItemCreate(BaseModel):
    segment_id: str
    job_id: str | None = None
    provider_id: str
    external_id: str | None = None
    query: str
    source_url: str | None = None
    title: str | None = None
    raw_payload: dict[str, Any]
    fetched_at: datetime


class SourceItemDecisionCreate(BaseModel):
    stage: SourceItemStage
    decision: SourceItemDecisionValue
    reason: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)
    details: dict[str, Any] = Field(default_factory=dict)
    actor_type: str = "system"
    actor_id: str | None = None


class SourceItemDecisionRead(SourceItemDecisionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_item_id: str
    created_at: datetime
    updated_at: datetime


class SourceItemRead(SourceItemCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    content_hash: str
    state: SourceItemState
    business_id: str | None = None
    last_error: str | None = None
    decisions: list[SourceItemDecisionRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class SourceItemReviewAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DUPLICATE = "duplicate"
    REAUDIT = "reaudit"


class SourceItemReview(BaseModel):
    action: SourceItemReviewAction
    reason: str | None = None
