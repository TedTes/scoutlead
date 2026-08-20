from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from campaign_sources.schemas import CampaignSourceMode, CampaignSourceSlot


class SourcePresetSource(BaseModel):
    slot: CampaignSourceSlot
    provider_id: str = Field(min_length=1)
    mode: CampaignSourceMode
    input: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    budget_limit: float | None = Field(default=None, ge=0)


class SourcePreset(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    sources: list[SourcePresetSource] = Field(default_factory=list)

