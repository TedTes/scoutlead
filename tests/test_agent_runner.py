from agents.runner import BoundedAgentRunner, StopAction, ToolAction


class FailingTool:
    name = "source"

    def execute(self, args):
        del args
        raise RuntimeError("provider unavailable")


def test_runner_can_continue_after_a_recoverable_tool_error() -> None:
    errors = []

    def decide(state, iteration):
        if state["attempts"]:
            return StopAction("done")
        return ToolAction(tool_name="source", args={}, reason="test source")

    def observe(state, action, observation, iteration):
        del action, iteration
        assert observation["error_type"] == "RuntimeError"
        return {"attempts": state["attempts"] + 1}

    result = BoundedAgentRunner().run(
        goal="test",
        initial_state={"attempts": 0},
        max_iterations=2,
        allowed_tools={"source"},
        tools=[FailingTool()],
        decide=decide,
        observe=observe,
        on_tool_start=lambda action, iteration: "call_1",
        on_tool_error=lambda call_id, error: errors.append((call_id, str(error))),
        continue_on_tool_error=True,
    )

    assert result.stopped is True
    assert result.state["attempts"] == 1
    assert errors == [("call_1", "provider unavailable")]
