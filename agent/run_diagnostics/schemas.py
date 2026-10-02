from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from leads.schemas import LeadRead


class RunPipelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    segment_id: str | None = None
    job_id: str | None = None
    stage: str
    event_type: str
    status: str
    provider_id: str | None = None
    business_id: str | None = None
    lead_id: str | None = None
    item_key: str | None = None
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    reason: str | None = None
    created_at: datetime
    updated_at: datetime


class RunSourceDiagnostic(BaseModel):
    key: str
    provider_id: str
    query: str
    quota: int
    status: str
    fetched_count: int
    accepted_count: int | None = None
    rejected_count: int | None = None
    written_count: int
    final_count: int
    failure: str | None = None
    request: dict[str, Any]
    state: dict[str, Any]
    exact_decisions: bool


class RunJobDiagnostic(BaseModel):
    id: str
    type: str
    status: str
    attempts: int
    max_attempts: int
    payload: dict[str, Any]
    last_error: str | None = None
    run_after: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RunDiagnostics(BaseModel):
    run_id: str
    run_name: str
    run_status: str
    run_stage: str
    created_at: datetime
    updated_at: datetime
    retention: str
    request: dict[str, Any]
    segment: dict[str, Any] | None = None
    summary: dict[str, int | None]
    sources: list[RunSourceDiagnostic]
    jobs: list[RunJobDiagnostic]
    events: list[RunPipelineEventRead]
    final_results: list[LeadRead]
    caveats: list[str]
