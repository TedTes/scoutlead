from datetime import datetime
from enum import StrEnum

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
    preferred_discovery_sources: list[DiscoverySource] = Field(min_length=1)
    outreach_objective: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)

    @field_validator("constraints")
    @classmethod
    def non_empty_constraints(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class ProductCreate(ProductBase):
    pass


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


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
