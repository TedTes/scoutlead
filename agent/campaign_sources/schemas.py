from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CampaignSourceSlot(StrEnum):
    DISCOVERY = "discovery"
    CONTACT = "contact"
    VERIFY = "verify"
    SIGNAL = "signal"


class CampaignSourceMode(StrEnum):
    ACCUMULATE = "accumulate"
    FIRST_GOOD = "first_good"


class CampaignSourceCreate(BaseModel):
    campaign_id: str = Field(min_length=1)
    slot: CampaignSourceSlot
    provider_id: str = Field(min_length=1)
    mode: CampaignSourceMode
    input: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    budget_limit: float | None = Field(default=None, ge=0)


class CampaignSourceRead(CampaignSourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
