from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from audience_runs.schemas import AudienceLeadRead
from job_queue.schemas import QueueJobRead


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


class ProfileBatchState(StrEnum):
    SETUP = "setup"
    SCORING = "scoring"
    RETRYING = "retrying"
    READY = "ready"
    EMPTY = "empty"
    PARTIAL = "partial"
    FAILED = "failed"


class ProfileCustomerKind(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    BOTH = "both"


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
    folder_id: str | None = Field(default=None, min_length=1)
    niche_id: str | None = None
    niche_slug: str = Field(min_length=1)
    niche_label: str = Field(min_length=1)
    niche_category: str | None = None
    market_key: str = Field(min_length=1)
    city: str | None = None
    place_label: str | None = Field(default=None, max_length=500)
    place_provider: str | None = Field(default=None, max_length=64)
    place_external_id: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: int = Field(default=25, ge=1, le=250)
    customer_kind: ProfileCustomerKind = ProfileCustomerKind.RESIDENTIAL
    service_keys: list[str] = Field(default_factory=list)
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

    @model_validator(mode="after")
    def require_complete_coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        return self


class TerritoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1)
    folder_id: str | None = Field(default=None, min_length=1)
    status: TerritoryStatus | None = None
    batch_size: int | None = Field(default=None, ge=1, le=100)
    min_fit: TerritoryMinFit | None = None
    niche_id: str | None = Field(default=None, min_length=1)
    city: str | None = Field(default=None, min_length=1)
    place_label: str | None = Field(default=None, min_length=1, max_length=500)
    place_provider: str | None = Field(default=None, min_length=1, max_length=64)
    place_external_id: str | None = Field(default=None, min_length=1, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: int | None = Field(default=None, ge=1, le=250)
    customer_kind: ProfileCustomerKind | None = None
    service_keys: list[str] | None = None
    signal_keys: list[str] | None = None
    exclusion_keys: list[str] | None = None
    refill_policy: TerritoryRefillPolicy | None = None

    @model_validator(mode="after")
    def require_complete_coordinate_pair(self):
        provided = self.model_fields_set
        if "latitude" in provided or "longitude" in provided:
            if "latitude" not in provided or "longitude" not in provided:
                raise ValueError("latitude and longitude must be updated together")
            if (self.latitude is None) != (self.longitude is None):
                raise ValueError("latitude and longitude must be provided together")
        return self


class TerritoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    product_id: str
    folder_id: str | None = None
    niche_id: str
    niche_label: str | None = None
    market_key: str
    city: str
    place_label: str | None = None
    place_provider: str | None = None
    place_external_id: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: int
    customer_kind: ProfileCustomerKind = ProfileCustomerKind.RESIDENTIAL
    service_keys: list[str] = Field(default_factory=list)
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
    last_batch_count: int = 0
    unreviewed_batch_count: int = 0
    positive_outcome_rate: float = 0.0
    created_at: datetime
    updated_at: datetime


class ProfileMarket(BaseModel):
    place_label: str = Field(min_length=2, max_length=500)
    place_provider: str = Field(min_length=1, max_length=64)
    place_external_id: str | None = Field(default=None, max_length=255)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: int = Field(default=25, ge=1, le=250)

    @field_validator("place_label")
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
    folder_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    niche_id: str = Field(min_length=1)
    customer_kind: ProfileCustomerKind
    market: ProfileMarket
    services: list[str] = Field(default_factory=list, max_length=20)
    signals: list[str] = Field(default_factory=list, max_length=50)
    exclude: list[ProfileExclusion] = Field(
        default_factory=lambda: list(ProfileExclusion)
    )
    limit: int = Field(default=25, ge=1, le=100)
    refill_policy: TerritoryRefillPolicy = TerritoryRefillPolicy.WHEN_DEPLETED
    exclude_already_delivered: Literal[True] = True
    clone_from_id: str | None = Field(default=None, min_length=1)


class AudienceFolderCreate(BaseModel):
    product_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)


class AudienceFolderUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class AudienceFolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    product_id: str
    name: str
    sort_order: int
    audience_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProfileBusinessTypeOptionRead(BaseModel):
    id: str
    key: str
    label: str
    category: str | None = None


class ProfileSignalOptionRead(BaseModel):
    key: str
    label: str
    category: str


class ProfileServiceSignalRead(BaseModel):
    key: str
    label: str
    weight: float = 1.0


class ProfileServiceOptionRead(BaseModel):
    key: str
    label: str
    description: str | None = None
    status: Literal["draft", "active", "inactive"]
    enabled: bool
    signals: list[ProfileServiceSignalRead] = Field(default_factory=list)


class ProfileOptionsRead(BaseModel):
    business_types: list[ProfileBusinessTypeOptionRead]
    services: list[ProfileServiceOptionRead] = Field(default_factory=list)
    opportunity_signals: list[ProfileSignalOptionRead] = Field(default_factory=list)
    radius_presets: list[int] = Field(default_factory=lambda: [10, 25, 50])
    radius_min: int = 1
    radius_max: int = 250
    batch_size_presets: list[int] = Field(default_factory=lambda: [15, 25, 40])
    batch_size_min: int = 1
    batch_size_max: int = 100


class PlaceRead(BaseModel):
    label: str
    provider: str
    external_id: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float


class ProfileQueuedRead(BaseModel):
    audience: TerritoryRead
    job: QueueJobRead


class ProfileBatchRead(BaseModel):
    audience: TerritoryRead
    audience_run_id: str | None = None
    outreach_campaign_id: str | None = None
    leads: list[AudienceLeadRead] = Field(default_factory=list)
    state: ProfileBatchState
    requested_count: int
    result_count: int
    remaining_count: int
    failure_class: Literal["rate_limit", "quota", "other"] | None = None
    retry_at: datetime | None = None
