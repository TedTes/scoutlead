from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentRunKind(StrEnum):
    CAMPAIGN = "campaign"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolCallStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunCreate(BaseModel):
    campaign_id: str = Field(min_length=1)
    objective: str | None = None
    max_tool_calls: int = Field(default=50, gt=0, le=1000)
    max_llm_calls: int = Field(default=50, gt=0, le=1000)
    max_leads: int | None = Field(default=None, gt=0, le=1000)


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str
    product_id: str
    kind: AgentRunKind
    objective: str
    status: AgentRunStatus
    current_phase: str | None = None
    context_snapshot: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    max_tool_calls: int
    max_llm_calls: int
    max_leads: int
    tool_call_count: int
    llm_call_count: int
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    campaign_id: str
    phase: str
    status: AgentStepStatus
    sequence: int
    objective: str
    input_snapshot: dict[str, Any]
    output_snapshot: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ToolCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    step_id: str | None = None
    campaign_id: str
    tool_name: str
    status: ToolCallStatus
    reason: str | None = None
    args: dict[str, Any]
    observation: dict[str, Any] | list[Any] | str | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunDetail(AgentRunRead):
    steps: list[AgentStepRead] = Field(default_factory=list)
    tool_calls: list[ToolCallRead] = Field(default_factory=list)
