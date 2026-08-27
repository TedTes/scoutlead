from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from campaigns.schemas import CampaignRead, CampaignRunSummary


GOOGLE_PLACES_PROVIDER_ID = "google_places"


class SourceRequestAction(StrEnum):
    LIST_CONTACTS = "list_contacts"


class SourceProviderKind(StrEnum):
    TEXT_QUERY = "text_query"
    URL_LIST = "url_list"
    SEARCH_URL = "search_url"
    CLASSIFIED_SEARCH_URL = "classified_search_url"


class SourceRequestCreate(BaseModel):
    product_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    prompt: str = Field(min_length=3)
    max_results: int = Field(default=25, gt=0, le=100)
    run_immediately: bool = True


class SourceRequestIntent(BaseModel):
    business_category: str = Field(min_length=1)
    location: str = ""
    country: str = ""
    required_signals: list[str] = Field(default_factory=list)
    excluded_result_types: list[str] = Field(default_factory=list)
    search_query: str = Field(min_length=1)
    search_url: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    rationale: str = Field(min_length=1)


class SourceRequestPlan(BaseModel):
    source: str = Field(min_length=1)
    action: SourceRequestAction = SourceRequestAction.LIST_CONTACTS
    query: str = Field(min_length=1)
    max_results: int
    source_preset_id: str
    explanation: str
    intent: SourceRequestIntent | None = None
    source_inputs: dict[str, Any] = Field(default_factory=dict)


class SourceProviderRead(BaseModel):
    id: str
    label: str
    configured: bool
    detail: str | None = None


class SourceRequestRun(BaseModel):
    plan: SourceRequestPlan
    run: CampaignRead
    summary: CampaignRunSummary | None = None
