from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QualityReviewCandidate(BaseModel):
    business_id: str
    display_name: str
    address: str | None = None
    phone: str | None = None
    website_url: str | None = None
    dimension: str
    predicted: Any | None = None
    source: str | None = None
    niche_id: str
    niche_label: str
    market_key: str
    publication_status: str
    publication_reasons: list[dict] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)


class QualityLabelCreate(BaseModel):
    business_id: str
    dimension: str
    expected: Any
    predicted: Any | None = None
    source: str | None = None
    niche_id: str | None = None
    market_key: str | None = None
    validator_version: int | None = None
    evidence: list[str] = Field(default_factory=list)
    notes: str | None = None


class QualityMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dimension: str
    source: str | None = None
    niche_id: str | None = None
    market_key: str | None = None
    validator_version: int | None = None
    sample_size: int
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    precision: float | None = None
    recall: float | None = None
    precision_lower_bound: float | None = None
    calculated_at: datetime


class QualityOverview(BaseModel):
    businesses: int
    source_observations: int
    fact_claims: int
    facts_by_resolution: dict[str, int] = Field(default_factory=dict)
    facts_by_quality: dict[str, int] = Field(default_factory=dict)
    validations_by_status: dict[str, int] = Field(default_factory=dict)
    publications_by_status: dict[str, int] = Field(default_factory=dict)
    source_items_by_state: dict[str, int] = Field(default_factory=dict)
    audience_runs_by_state: dict[str, int] = Field(default_factory=dict)
    queue_jobs_by_status: dict[str, int] = Field(default_factory=dict)
    expired_facts: int
    expired_publications: int
    latest_global_metrics: dict[str, QualityMetricRead] = Field(default_factory=dict)
