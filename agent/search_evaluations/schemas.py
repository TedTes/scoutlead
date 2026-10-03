from enum import StrEnum

from pydantic import BaseModel, Field


class SearchEvaluationStatus(StrEnum):
    MATCHED = "matched"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class SearchCriterionEvaluation(BaseModel):
    criterion: str = Field(min_length=1)
    matched: bool | None
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class SearchEvaluationResult(BaseModel):
    status: SearchEvaluationStatus
    confidence: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)
    criteria: list[SearchCriterionEvaluation] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
