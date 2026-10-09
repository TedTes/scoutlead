from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from job_queue.schemas import QueueJobRead
from audience_runs.schemas import AudienceLeadRead
from leads.schemas import LeadRead


class TerritoryStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class TerritoryCadence(StrEnum):
    WEEKLY = "weekly"


class TerritoryRefillPolicy(StrEnum):
    MANUAL = "manual"
    WHEN_DEPLETED = "when_depleted"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class TerritoryMinFit(StrEnum):
    GOOD_FIT = "good_fit"
    MAYBE = "maybe"


class TerritoryDeliveryStatus(StrEnum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    READY = "ready"
    EMPTY = "empty"
    PARTIAL = "partial"
    FAILED = "failed"


class ProfileBatchState(StrEnum):
    SETUP = "setup"
    SCORING = "scoring"
    RETRYING = "retrying"
    READY = "ready"
    EMPTY = "empty"
    PARTIAL = "partial"
    FAILED = "failed"


class ProfileTrade(StrEnum):
    PAINTERS = "painters"
    HVAC = "hvac"
    ROOFERS = "roofers"
    PLUMBERS = "plumbers"
    ELECTRICIANS = "electricians"


class ProfileCustomerKind(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"


class ProfileSignal(StrEnum):
    WEBSITE_UNAVAILABLE = "website_unavailable"
    NO_QUOTE_FLOW = "no_quote_flow"
    NO_CONTACT_FORM = "no_contact_form"
    REVIEWS_UNDER_15 = "reviews_under_15"


class ProfileExclusion(StrEnum):
    CLOSED = "closed"
    CHAINS = "chains"
    FRANCHISES = "franchises"
    DIRECTORIES = "directories"
    AGENCIES = "agencies"


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
    city: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: int = Field(default=25, ge=1, le=250)
    trade_keys: list[str] = Field(default_factory=list)
    customer_kind: ProfileCustomerKind = ProfileCustomerKind.RESIDENTIAL
    signal_keys: list[str] = Field(default_factory=list)
    exclusion_keys: list[str] = Field(default_factory=list)
    label: str | None = Field(default=None, min_length=1)
    confirmed: bool = False
    status: TerritoryStatus = TerritoryStatus.ACTIVE
    cadence: TerritoryCadence = TerritoryCadence.WEEKLY
    refill_policy: TerritoryRefillPolicy = TerritoryRefillPolicy.WHEN_DEPLETED
    batch_size: int = Field(default=25, ge=1, le=100)
    min_fit: TerritoryMinFit = TerritoryMinFit.MAYBE
    request: str | None = None
    search_contract: dict = Field(default_factory=dict)
    evidence_max_age_days: int = Field(default=30, ge=1, le=365)
    criteria_hash: str = "default"
    criteria_version: int = Field(default=1, ge=1)


class TerritoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1)
    status: TerritoryStatus | None = None
    batch_size: int | None = Field(default=None, ge=1, le=100)
    min_fit: TerritoryMinFit | None = None
    city: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: int | None = Field(default=None, ge=1, le=250)
    trade_keys: list[ProfileTrade] | None = Field(default=None, min_length=1)
    customer_kind: ProfileCustomerKind | None = None
    signal_keys: list[str] | None = None
    exclusion_keys: list[str] | None = None
    refill_policy: TerritoryRefillPolicy | None = None


class TerritoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    product_id: str
    niche_id: str
    market_key: str
    city: str
    latitude: float | None = None
    longitude: float | None = None
    radius_km: int
    trade_keys: list[str] = Field(default_factory=list)
    customer_kind: ProfileCustomerKind = ProfileCustomerKind.RESIDENTIAL
    signal_keys: list[str] = Field(default_factory=list)
    exclusion_keys: list[str] = Field(default_factory=list)
    label: str
    status: TerritoryStatus
    cadence: TerritoryCadence
    refill_policy: TerritoryRefillPolicy
    batch_size: int
    min_fit: TerritoryMinFit
    search_prompt: str | None = None
    search_contract: dict = Field(default_factory=dict)
    evidence_max_age_days: int = 30
    criteria_hash: str = "default"
    criteria_version: int = 1
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


class ProfileMarket(BaseModel):
    city: str = Field(min_length=2, max_length=255)
    radius_km: Literal[10, 25, 50] = 25

    @field_validator("city")
    @classmethod
    def require_one_city(cls, value: str) -> str:
        city = " ".join(value.split())
        broad_markets = {
            "canada",
            "united states",
            "united states of america",
            "usa",
            "us",
            "united states canada",
            "canada united states",
        }
        normalized = " ".join(
            city.lower().replace(",", " ").replace("&", " ").split()
        )
        if not city or normalized in broad_markets or ";" in city or "|" in city:
            raise ValueError("market must identify one city")
        return city


class ProfileCreate(BaseModel):
    product_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    trades: list[ProfileTrade] = Field(min_length=1, max_length=5)
    customer_kind: ProfileCustomerKind
    market: ProfileMarket
    signals: list[ProfileSignal] = Field(default_factory=list)
    exclude: list[ProfileExclusion] = Field(
        default_factory=lambda: list(ProfileExclusion)
    )
    limit: Literal[15, 25, 40] = 25
    refill_policy: TerritoryRefillPolicy = TerritoryRefillPolicy.WHEN_DEPLETED
    exclude_already_delivered: Literal[True] = True


class ProfileBusinessTypeOptionRead(BaseModel):
    key: ProfileTrade
    label: str


class ProfileOptionsRead(BaseModel):
    business_types: list[ProfileBusinessTypeOptionRead]


class ProfileQueuedRead(BaseModel):
    profile: TerritoryRead
    job: QueueJobRead


class ProfileBatchRead(BaseModel):
    profile: TerritoryRead
    delivery: TerritoryDeliveryRead | None = None
    audience_run_id: str | None = None
    outreach_campaign_id: str | None = None
    leads: list[AudienceLeadRead] = Field(default_factory=list)
    state: ProfileBatchState
    requested_count: int
    result_count: int
    remaining_count: int
    failure_class: Literal["rate_limit", "quota", "other"] | None = None
    retry_at: datetime | None = None
