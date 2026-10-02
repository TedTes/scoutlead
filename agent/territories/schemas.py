from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TerritoryStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"


class TerritoryCadence(StrEnum):
    WEEKLY = "weekly"


class TerritoryMinFit(StrEnum):
    GOOD_FIT = "good_fit"
    MAYBE = "maybe"


class TerritoryDeliveryStatus(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class TerritoryResolveRequest(BaseModel):
    product_id: str = Field(min_length=1)
    request: str = Field(min_length=3)


class TerritoryResolutionRead(BaseModel):
    product_id: str
    request: str
    niche_id: str | None = None
    niche_slug: str
    niche_label: str
    niche_category: str
    market_key: str
    market_label: str
    confidence: float = Field(ge=0, le=1)
    existing_niche: bool
    requires_confirmation: bool = True


class TerritoryCreate(BaseModel):
    product_id: str = Field(min_length=1)
    niche_id: str | None = None
    niche_slug: str = Field(min_length=1)
    niche_label: str = Field(min_length=1)
    niche_category: str | None = None
    market_key: str = Field(min_length=1)
    label: str | None = Field(default=None, min_length=1)
    confirmed: bool = False
    status: TerritoryStatus = TerritoryStatus.ACTIVE
    cadence: TerritoryCadence = TerritoryCadence.WEEKLY
    batch_size: int = Field(default=25, ge=1, le=100)
    min_fit: TerritoryMinFit = TerritoryMinFit.MAYBE
    request: str | None = None
    search_contract: dict = Field(default_factory=dict)
    evidence_max_age_days: int = Field(default=30, ge=1, le=365)
    criteria_hash: str = "default"


class TerritoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1)
    status: TerritoryStatus | None = None
    batch_size: int | None = Field(default=None, ge=1, le=100)
    min_fit: TerritoryMinFit | None = None


class TerritoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    product_id: str
    niche_id: str
    market_key: str
    label: str
    status: TerritoryStatus
    cadence: TerritoryCadence
    batch_size: int
    min_fit: TerritoryMinFit
    search_prompt: str | None = None
    search_contract: dict = Field(default_factory=dict)
    evidence_max_age_days: int = 30
    criteria_hash: str = "default"
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_delivery_count: int = 0
    unviewed_delivery_count: int = 0
    positive_outcome_rate: float = 0.0
    created_at: datetime
    updated_at: datetime


class TerritoryDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    territory_id: str
    campaign_id: str
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    delivered_at: datetime | None = None
    viewed_at: datetime | None = None
    new_contact_count: int
    status: TerritoryDeliveryStatus
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class TerritoryRefreshRead(BaseModel):
    territory: TerritoryRead
    delivery: TerritoryDeliveryRead
