from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from campaigns.schemas import CampaignRead, CampaignRunSummary


GOOGLE_PLACES_PROVIDER_ID = "google_places"


class SourceRequestAction(StrEnum):
    LIST_CONTACTS = "list_contacts"


class SourceRequestCreate(BaseModel):
    product_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    prompt: str = Field(min_length=3)
    max_results: int = Field(default=25, gt=0, le=100)
    run_immediately: bool = True


class SourceRequestPlan(BaseModel):
    source: str = Field(min_length=1)
    action: SourceRequestAction = SourceRequestAction.LIST_CONTACTS
    query: str = Field(min_length=1)
    max_results: int
    source_preset_id: str
    explanation: str


class SourceProviderRead(BaseModel):
    id: str
    label: str
    configured: bool
    detail: str | None = None


class SourceRequestRun(BaseModel):
    plan: SourceRequestPlan
    run: CampaignRead
    summary: CampaignRunSummary | None = None
