from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from campaigns.schemas import CampaignRead, CampaignRunSummary


GOOGLE_PLACES_PROVIDER_ID = "google_places"
AUTO_PROVIDER_ID = "auto"
OPENSTREETMAP_PROVIDER_ID = "openstreetmap"
CONFIGURED_SEARCH_PROVIDER_ID = "configured_search"


class SourceRequestAction(StrEnum):
    LIST_CONTACTS = "list_contacts"


class SourceProviderKind(StrEnum):
    TEXT_QUERY = "text_query"
    URL_LIST = "url_list"
    SEARCH_URL = "search_url"
    CLASSIFIED_SEARCH_URL = "classified_search_url"


class SearchCriterionMode(StrEnum):
    REQUIRED = "required"
    ALTERNATIVE = "alternative"
    EXCLUDED = "excluded"


class SearchIntentCriterion(BaseModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    mode: SearchCriterionMode
    fact_key: str | None = None
    operator: str | None = None
    value: str | float | bool | list[str] | None = None
    evidence_requirement: str = Field(default="Public business evidence", min_length=1)


class SourceRequestIntent(BaseModel):
    schema_version: int = Field(default=1, ge=1)
    business_category: str = Field(min_length=1)
    location: str = ""
    country: str = ""
    included_subcategories: list[str] = Field(default_factory=list)
    criteria: list[SearchIntentCriterion] = Field(default_factory=list)
    contact_requirements: list[str] = Field(default_factory=list)
    required_signals: list[str] = Field(default_factory=list)
    excluded_result_types: list[str] = Field(default_factory=list)
    search_query: str = Field(min_length=1)
    search_url: str = ""
    confidence: int = Field(default=0, ge=0, le=100)
    rationale: str = Field(min_length=1)


class SourceRequestCreate(BaseModel):
    product_id: str = Field(min_length=1)
    source: str = Field(default=AUTO_PROVIDER_ID, min_length=1)
    prompt: str = Field(min_length=3)
    name: str | None = Field(default=None, min_length=1)
    max_results: int = Field(default=25, gt=0, le=100)
    run_immediately: bool = True
    business_category: str | None = None
    geography: str | None = None
    opportunity_type: str | None = None
    evidence_max_age_days: int = Field(default=30, ge=1, le=365)
    intent_override: SourceRequestIntent | None = None


class SourceTask(BaseModel):
    provider_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    stage: int = Field(default=1, ge=1)
    priority: int = Field(default=100, ge=0)
    max_results: int = Field(gt=0, le=100)
    reason: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    budget_limit: float | None = Field(default=None, ge=0)


class SourceRequestPlan(BaseModel):
    source: str = Field(min_length=1)
    action: SourceRequestAction = SourceRequestAction.LIST_CONTACTS
    query: str = Field(min_length=1)
    max_results: int
    source_preset_id: str
    explanation: str
    intent: SourceRequestIntent | None = None
    source_inputs: dict[str, Any] = Field(default_factory=dict)
    tasks: list[SourceTask] = Field(default_factory=list)


class SourceProviderRead(BaseModel):
    id: str
    label: str
    configured: bool
    detail: str | None = None


class SourceRequestRun(BaseModel):
    plan: SourceRequestPlan
    run: CampaignRead
    summary: CampaignRunSummary | None = None
    state: str = "ready"
    current_result_count: int = 0
    requested_result_count: int = 0
    contract_hash: str = ""
    interpreted_intent: SourceRequestIntent | None = None
    unsupported_criteria: list[str] = Field(default_factory=list)
    unresolved_criteria: list[str] = Field(default_factory=list)
