from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from shared.errors import WorkflowBoundaryError


@dataclass(frozen=True)
class ToolAction:
    tool_name: str
    args: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class StopAction:
    reason: str


AgentAction = ToolAction | StopAction


class Tool(Protocol):
    name: str

    def execute(self, args: dict[str, Any]) -> Any:
        raise NotImplementedError


@dataclass
class AgentTraceEntry:
    iteration: int
    action: AgentAction
    observation: Any | None = None


@dataclass
class AgentRunResult:
    goal: str
    state: dict[str, Any]
    trace: list[AgentTraceEntry] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str | None = None


class BoundedAgentRunner:
    def run(
        self,
        *,
        goal: str,
        initial_state: dict[str, Any],
        max_iterations: int,
        allowed_tools: set[str],
        tools: list[Tool],
        decide: Callable[[dict[str, Any], int], AgentAction],
        observe: Callable[[dict[str, Any], ToolAction, Any, int], dict[str, Any]],
    ) -> AgentRunResult:
        tool_map = {tool.name: tool for tool in tools}
        state = dict(initial_state)
        trace: list[AgentTraceEntry] = []

        for iteration in range(max_iterations):
            action = decide(state, iteration)
            if isinstance(action, StopAction):
                trace.append(AgentTraceEntry(iteration=iteration, action=action))
                return AgentRunResult(
                    goal=goal,
                    state=state,
                    trace=trace,
                    stopped=True,
                    stop_reason=action.reason,
                )

            if action.tool_name not in allowed_tools:
                raise WorkflowBoundaryError(
                    f"tool is outside workflow boundary: {action.tool_name}",
                    {"allowed_tools": sorted(allowed_tools), "tool_name": action.tool_name},
                )
            tool = tool_map.get(action.tool_name)
            if tool is None:
                raise WorkflowBoundaryError(f"tool is not registered: {action.tool_name}")

            observation = tool.execute(action.args)
            trace.append(AgentTraceEntry(iteration=iteration, action=action, observation=observation))
            state = observe(state, action, observation, iteration)

        return AgentRunResult(
            goal=goal,
            state=state,
            trace=trace,
            stopped=False,
            stop_reason="max_iterations_reached",
        )
