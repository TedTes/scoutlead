from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from icp.schemas import SlotConfig
from orchestration.budget import BudgetTracker
from orchestration.confidence import dedupe_results
from tools.base import ToolAdapter, ToolExecutionMode, ToolResult


@dataclass
class SlotRunResult:
    slot: str
    mode: str
    accepted: list[ToolResult] = field(default_factory=list)
    rejected: list[ToolResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def data(self) -> list[Any]:
        values: list[Any] = []
        for result in self.accepted:
            if isinstance(result.data, list):
                values.extend(result.data)
            else:
                values.append(result.data)
        return dedupe_results(values)

    def model_dump(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "mode": self.mode,
            "accepted": [result.model_dump() for result in self.accepted],
            "rejected": [result.model_dump() for result in self.rejected],
            "errors": self.errors,
            "data": self.data,
        }


class SlotRunner:
    def run(
        self,
        *,
        config: SlotConfig,
        context: dict[str, Any],
        tools: list[ToolAdapter],
        budget: BudgetTracker | None = None,
        on_tool_start: Callable[[str, dict[str, Any], str], str | None] | None = None,
        on_tool_success: Callable[[str, ToolResult], None] | None = None,
        on_tool_error: Callable[[str, Exception], None] | None = None,
    ) -> SlotRunResult:
        budget = budget or BudgetTracker(
            max_cost_usd=config.max_cost_usd,
            max_tool_calls=config.max_calls,
        )
        result = SlotRunResult(slot=config.slot.value, mode=config.mode.value)
        enabled_tools = [tool for tool in tools if tool.name in {item.name for item in config.tools if item.enabled}]

        for tool in enabled_tools:
            tool_call_id: str | None = None
            try:
                budget.assert_can_call()
                if on_tool_start:
                    tool_call_id = on_tool_start(
                        tool.name,
                        {"slot": config.slot.value, "mode": config.mode.value, **context},
                        f"{config.mode.value} {config.slot.value} slot via {tool.name}",
                    )
                tool_result = tool.run(context)
                budget.record(tool_result)
            except Exception as exc:
                if tool_call_id and on_tool_error:
                    on_tool_error(tool_call_id, exc)
                result.errors.append({"tool": tool.name, "error": str(exc)})
                continue
            if tool_call_id and on_tool_success:
                on_tool_success(tool_call_id, tool_result)

            if config.mode == ToolExecutionMode.FIRST_GOOD:
                if tool_result.meets_confidence(config.confidence_threshold):
                    result.accepted.append(tool_result)
                    break
                result.rejected.append(tool_result)
                continue

            if tool_result.confidence >= config.confidence_threshold:
                result.accepted.append(tool_result)
            else:
                result.rejected.append(tool_result)
            if len(result.data) >= config.target_count:
                break

        return result
