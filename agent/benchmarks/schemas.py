from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


TruthValue = Literal["yes", "no", "unknown"]
WebsiteTruth = Literal[
    "present",
    "missing",
    "unavailable",
    "parked",
    "not_listed",
    "unknown",
]


class BenchmarkObserved(BaseModel):
    trade_keys: list[str] = Field(default_factory=list)
    customer_kind: str | None = None
    operational: bool | None = None
    website_status: str | None = None
    quote_or_booking_form_present: bool | None = None
    contact_form_present: bool | None = None
    review_count: int | None = None
    is_chain: bool | None = None
    is_franchise: bool | None = None
    is_directory: bool | None = None
    is_agency: bool | None = None


class BenchmarkLabels(BaseModel):
    identity_correct: TruthValue = "unknown"
    trade_correct: TruthValue = "unknown"
    location_correct: TruthValue = "unknown"
    customer_kind: Literal["residential", "commercial", "both", "unknown"] = "unknown"
    operational: TruthValue = "unknown"
    website_status: WebsiteTruth = "unknown"
    quote_or_booking_form_present: TruthValue = "unknown"
    contact_form_present: TruthValue = "unknown"
    review_count: int | None = Field(default=None, ge=0)
    is_chain: TruthValue = "unknown"
    is_franchise: TruthValue = "unknown"
    is_directory: TruthValue = "unknown"
    is_agency: TruthValue = "unknown"
    source_urls: list[str] = Field(default_factory=list)
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def require_review_metadata(self):
        values = self.model_dump(exclude={"source_urls", "reviewer", "reviewed_at", "notes"})
        is_labeled = any(value not in {None, "unknown"} for value in values.values())
        if is_labeled and (not self.reviewer or self.reviewed_at is None):
            raise ValueError("reviewer and reviewed_at are required once labels are assigned")
        return self


class BenchmarkRecord(BaseModel):
    benchmark_version: str = "business-accuracy-v1"
    business_id: str
    sampled_niche: str | None = None
    market_key: str | None = None
    display_name: str
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    website_url: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    observed: BenchmarkObserved
    labels: BenchmarkLabels = Field(default_factory=BenchmarkLabels)


class MetricResult(BaseModel):
    labeled: int = 0
    correct: int = 0
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    unknown_prediction: int = 0
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None


class BenchmarkGate(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)


class BenchmarkCoverage(BaseModel):
    reviewed_by_niche: dict[str, int] = Field(default_factory=dict)
    reviewed_by_market: dict[str, int] = Field(default_factory=dict)


class BenchmarkReport(BaseModel):
    benchmark_version: str
    record_count: int
    reviewed_count: int
    coverage: BenchmarkCoverage = Field(default_factory=BenchmarkCoverage)
    metrics: dict[str, MetricResult]
    gate: BenchmarkGate
