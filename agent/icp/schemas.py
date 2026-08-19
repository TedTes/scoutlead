from __future__ import annotations

from pydantic import BaseModel, Field

from tools.base import ToolExecutionMode, ToolSlot


class ToolConfig(BaseModel):
    name: str
    provider: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)


class SlotConfig(BaseModel):
    slot: ToolSlot
    mode: ToolExecutionMode
    tools: list[ToolConfig] = Field(default_factory=list)
    confidence_threshold: int = Field(default=70, ge=0, le=100)
    target_count: int = Field(default=25, ge=1, le=1000)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_calls: int | None = Field(default=None, ge=1)


class BudgetConfig(BaseModel):
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_tool_calls: int = Field(default=50, ge=1)


class ICPPreset(BaseModel):
    id: str
    name: str
    description: str | None = None
    slots: list[SlotConfig]
    budget: BudgetConfig = Field(default_factory=BudgetConfig)

    def slot_config(self, slot: ToolSlot) -> SlotConfig | None:
        return next((config for config in self.slots if config.slot == slot), None)
