from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryCandidateType(StrEnum):
    TARGET_BUSINESS = "target_business"
    COMPETITOR = "competitor"
    VENDOR = "vendor"
    DIRECTORY = "directory"
    CONTENT = "content"
    SALARY = "salary"
    JOB = "job"
    SOCIAL = "social"
    IRRELEVANT = "irrelevant"
    UNKNOWN = "unknown"


class CandidateAssessment(BaseModel):
    candidate_type: DiscoveryCandidateType
    confidence: int = Field(ge=0, le=100)
    rejection_reason: str | None = None

    @property
    def is_promotable(self) -> bool:
        return self.candidate_type == DiscoveryCandidateType.TARGET_BUSINESS and self.confidence >= 65


class DiscoveryCandidateCreate(BaseModel):
    campaign_id: str
    product_id: str
    query: str
    title: str
    url: str | None = None
    snippet: str | None = None
    geography: str | None = None
    contact_email: str | None = None
    source: str
    raw: dict[str, Any] = Field(default_factory=dict)
    candidate_type: DiscoveryCandidateType
    confidence: int = Field(ge=0, le=100)
    rejection_reason: str | None = None


class DiscoveryCandidateRead(DiscoveryCandidateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str | None = None
    promoted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
