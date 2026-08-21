from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DiscoverySourceType(StrEnum):
    WEB_SEARCH = "web_search"
    DIRECTORY = "directory"
    SEED = "seed"
    MANUAL = "manual"
    API = "api"


class DiscoverySource(BaseModel):
    type: DiscoverySourceType
    value: str = Field(min_length=1)
    limit: int | None = Field(default=None, gt=0)
    notes: str | None = None


class QualificationCriterion(BaseModel):
    id: str | None = None
    label: str = Field(min_length=1)
    description: str | None = None
    weight: float = Field(default=1.0, gt=0)
    required: bool = False
    evidence_required: bool = False


class ProductBase(BaseModel):
    product_name: str = Field(min_length=1)
    product_description: str = Field(min_length=1)
    target_customer: str = Field(min_length=1)
    problem_being_solved: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    target_geography: str = Field(min_length=1)
    validation_goal: str = Field(min_length=1)
    qualification_criteria: list[QualificationCriterion] = Field(min_length=1)
    preferred_discovery_sources: list[DiscoverySource] = Field(default_factory=list)
    outreach_objective: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    source_url: str | None = None
    source_fingerprint: str | None = None
    source_last_checked_at: datetime | None = None
    source_evidence: dict[str, Any] | None = None

    @field_validator("constraints")
    @classmethod
    def non_empty_constraints(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ProductCreate(ProductBase):
    pass


class ProductDescriptionCreate(BaseModel):
    product_name: str = Field(min_length=1)
    description: str = Field(min_length=20)
    target_geography: str = Field(default="United States, Canada", min_length=1)


class ProductSourceCreate(BaseModel):
    source: str = Field(min_length=1)
    context: str | None = Field(default=None, min_length=1)
    target_geography: str = Field(default="United States", min_length=1)


class ProductDiscoveryProvider(StrEnum):
    GOOGLE_PLACES = "google_places"
    CONFIGURED_SEARCH = "configured_search"


class ProductDiscoveryPlan(BaseModel):
    product_name: str = Field(min_length=1)
    product_description: str = Field(min_length=20)
    target_customer: str = Field(min_length=1)
    problem_being_solved: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    target_geography: str = Field(default="United States, Canada", min_length=1)
    validation_goal: str = Field(min_length=1)
    qualification_criteria: list[QualificationCriterion] = Field(min_length=1, max_length=6)
    discovery_query: str = Field(min_length=2)
    source_provider: ProductDiscoveryProvider = ProductDiscoveryProvider.CONFIGURED_SEARCH
    region_code: str | None = None
    outreach_objective: str = Field(default="Ask for a short customer discovery conversation.", min_length=1)
    rationale: str = Field(min_length=1)


class ProductDiscoveryStart(BaseModel):
    max_results: int = Field(default=10, gt=0, le=100)


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProductSourceEvidence(BaseModel):
    product_name_candidates: list[str] = Field(default_factory=list)
    headline: str | None = None
    claims: list[str] = Field(default_factory=list)
    target_customer_clues: list[str] = Field(default_factory=list)
    problem_clues: list[str] = Field(default_factory=list)
    value_clues: list[str] = Field(default_factory=list)
    source_snippets: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=0, le=100)
    missing_info: list[str] = Field(default_factory=list)
    rationale: str


class ProductInferenceRead(BaseModel):
    source: str
    context: str | None = None
    ready_to_save: bool
    confidence: int = Field(ge=0, le=100)
    missing_info: list[str] = Field(default_factory=list)
    evidence: ProductSourceEvidence
    product: ProductCreate
    existing_product: ProductRead | None = None


class ProductUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1)
    product_description: str | None = Field(default=None, min_length=1)
    target_customer: str | None = Field(default=None, min_length=1)
    problem_being_solved: str | None = Field(default=None, min_length=1)
    value_proposition: str | None = Field(default=None, min_length=1)
    target_geography: str | None = Field(default=None, min_length=1)
    validation_goal: str | None = Field(default=None, min_length=1)
    qualification_criteria: list[QualificationCriterion] | None = None
    preferred_discovery_sources: list[DiscoverySource] | None = None
    outreach_objective: str | None = Field(default=None, min_length=1)
    constraints: list[str] | None = None
    source_url: str | None = None
    source_fingerprint: str | None = None
    source_last_checked_at: datetime | None = None
    source_evidence: dict[str, Any] | None = None
