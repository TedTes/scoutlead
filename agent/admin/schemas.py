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
