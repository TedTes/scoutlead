from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AdminBusinessCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=255)
    niche_slug: str
    market_key: str = "toronto"
    geography: str | None = None
    address: str | None = None
    phone: str | None = None
    website_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source_url: str = Field(min_length=5, max_length=2000)
    source_provider: str = "admin_manual"
    reason: str = Field(min_length=3, max_length=1000)


class AdminBusinessUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=255)
    geography: str | None = None
    address: str | None = None
    phone: str | None = None
    website_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    customer_kind: str | None = None
    is_chain: bool | None = None
    is_franchise: bool | None = None
    is_directory: bool | None = None
    is_agency: bool | None = None
    reason: str = Field(min_length=3, max_length=1000)


class AdminBusinessStateChange(BaseModel):
    status: Literal["active", "quarantined", "archived"]
    reason: str = Field(min_length=3, max_length=1000)


class AdminActionReason(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdminDeleteRequest(BaseModel):
    confirmation: str
    reason: str = Field(min_length=3, max_length=1000)


class AdminDataJobCreate(BaseModel):
    segment_id: str
    processing_mode: Literal["automatic", "review_first"] = "review_first"
    reason: str = Field(min_length=3, max_length=1000)


class AdminDataJobAction(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    sample_size: int | None = Field(default=None, ge=1, le=100)
    source_item_ids: list[str] = Field(default_factory=list, max_length=200)


class AdminSignalDefinitionCreate(BaseModel):
    key: str = Field(min_length=2, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    value_type: Literal["boolean", "number", "text"]
    category: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    unit: str | None = Field(default=None, max_length=64)
    collector_key: str | None = Field(default=None, max_length=128)
    extractor_key: str | None = Field(default=None, max_length=128)
    freshness_days: int = Field(default=30, ge=1, le=3650)
    opportunity_direction: Literal[
        "none",
        "false_is_opportunity",
        "true_is_opportunity",
        "lower_is_opportunity",
        "higher_is_opportunity",
        "missing_is_opportunity",
    ] = "none"
    config: dict = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=1000)


class AdminSignalDefinitionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    unit: str | None = Field(default=None, max_length=64)
    collector_key: str | None = Field(default=None, max_length=128)
    extractor_key: str | None = Field(default=None, max_length=128)
    freshness_days: int | None = Field(default=None, ge=1, le=3650)
    opportunity_direction: Literal[
        "none",
        "false_is_opportunity",
        "true_is_opportunity",
        "lower_is_opportunity",
        "higher_is_opportunity",
        "missing_is_opportunity",
    ] | None = None
    config: dict | None = None
    reason: str = Field(min_length=3, max_length=1000)


class AdminSignalDefinitionStateChange(BaseModel):
    status: Literal["draft", "active", "inactive"]
    reason: str = Field(min_length=3, max_length=1000)
    scope: Literal["all", "selected", "segment"] = "all"
    business_ids: list[str] = Field(default_factory=list, max_length=500)
    niche_slug: str | None = None
    market_key: str | None = None
    batch_size: int = Field(default=25, ge=1, le=100)


class AdminSignalCollectionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    scope: Literal["all", "selected", "segment"] = "all"
    business_ids: list[str] = Field(default_factory=list, max_length=500)
    niche_slug: str | None = None
    market_key: str | None = None
    batch_size: int = Field(default=25, ge=1, le=100)


class AdminSignalValidationRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=1000)
    scope: Literal["all", "selected"] = "selected"
    business_ids: list[str] = Field(default_factory=list, max_length=500)
