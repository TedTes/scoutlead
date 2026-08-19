from __future__ import annotations

from dataclasses import dataclass

from shared.errors import WorkflowBoundaryError
from tools.base import ToolResult


@dataclass
class BudgetTracker:
    max_cost_usd: float | None = None
    max_tool_calls: int | None = None
    spent_usd: float = 0.0
    tool_calls: int = 0

    def assert_can_call(self) -> None:
        if self.max_tool_calls is not None and self.tool_calls >= self.max_tool_calls:
            raise WorkflowBoundaryError(
                "tool call budget reached",
                {"max_tool_calls": self.max_tool_calls, "tool_calls": self.tool_calls},
            )
        if self.max_cost_usd is not None and self.spent_usd >= self.max_cost_usd:
            raise WorkflowBoundaryError(
                "tool cost budget reached",
                {"max_cost_usd": self.max_cost_usd, "spent_usd": self.spent_usd},
            )

    def record(self, result: ToolResult) -> None:
        self.tool_calls += 1
        self.spent_usd += result.cost_usd
