from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_runs.schemas import AgentRunKind, AgentRunStatus, AgentStepStatus, ToolCallStatus
from db.models import AgentRunModel, AgentStepModel, ToolCallModel
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow


class AgentRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        campaign_id: str,
        product_id: str,
        objective: str,
        context_snapshot: dict[str, Any],
        max_tool_calls: int,
        max_llm_calls: int,
        max_leads: int,
    ) -> AgentRunModel:
        model = AgentRunModel(
            id=new_id("agent_run"),
            campaign_id=campaign_id,
            product_id=product_id,
            kind=AgentRunKind.CAMPAIGN.value,
            objective=objective,
            status=AgentRunStatus.QUEUED.value,
            current_phase=None,
            context_snapshot=context_snapshot,
            result=None,
            error=None,
            max_tool_calls=max_tool_calls,
            max_llm_calls=max_llm_calls,
            max_leads=max_leads,
            tool_call_count=0,
            llm_call_count=0,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[AgentRunModel]:
        statement = select(AgentRunModel).order_by(AgentRunModel.created_at.desc())
        return list(self.session.scalars(statement))

    def list_by_campaign(self, campaign_id: str) -> list[AgentRunModel]:
        statement = (
            select(AgentRunModel)
            .where(AgentRunModel.campaign_id == campaign_id)
            .order_by(AgentRunModel.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def list_steps(self, run_id: str) -> list[AgentStepModel]:
        statement = (
            select(AgentStepModel)
            .where(AgentStepModel.run_id == run_id)
            .order_by(AgentStepModel.sequence, AgentStepModel.created_at)
        )
        return list(self.session.scalars(statement))

    def list_tool_calls(self, run_id: str) -> list[ToolCallModel]:
        statement = (
            select(ToolCallModel)
            .where(ToolCallModel.run_id == run_id)
            .order_by(ToolCallModel.created_at)
        )
        return list(self.session.scalars(statement))

    def get(self, run_id: str) -> AgentRunModel:
        model = self.session.get(AgentRunModel, run_id)
        if model is None:
            raise NotFoundError("agent run not found", {"run_id": run_id})
        return model

    def claim_next(self) -> AgentRunModel | None:
        statement = (
            select(AgentRunModel)
            .where(AgentRunModel.status == AgentRunStatus.QUEUED.value)
            .order_by(AgentRunModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        model = self.session.scalar(statement)
        if model is None:
            return None
        model.status = AgentRunStatus.RUNNING.value
        model.started_at = model.started_at or utcnow()
        model.heartbeat_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def start(self, run_id: str) -> AgentRunModel:
        model = self.get(run_id)
        if model.status == AgentRunStatus.RUNNING.value:
            model.heartbeat_at = utcnow()
            self.session.commit()
            self.session.refresh(model)
            return model
        if model.status != AgentRunStatus.QUEUED.value:
            raise ConflictError(
                "only queued agent runs can be started",
                {"run_id": run_id, "status": model.status},
            )
        model.status = AgentRunStatus.RUNNING.value
        model.started_at = model.started_at or utcnow()
        model.heartbeat_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def heartbeat(self, run_id: str, *, phase: str | None = None) -> AgentRunModel:
        model = self.get(run_id)
        model.heartbeat_at = utcnow()
        if phase is not None:
            model.current_phase = phase
        self.session.commit()
        self.session.refresh(model)
        return model

    def complete(self, run_id: str, result: dict[str, Any]) -> AgentRunModel:
        model = self.get(run_id)
        model.status = AgentRunStatus.COMPLETED.value
        model.result = result
        model.error = None
        model.completed_at = utcnow()
        model.heartbeat_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def fail(self, run_id: str, error: str, result: dict[str, Any] | None = None) -> AgentRunModel:
        model = self.get(run_id)
        model.status = AgentRunStatus.FAILED.value
        model.error = error
        model.result = result
        model.completed_at = utcnow()
        model.heartbeat_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def cancel(self, run_id: str) -> AgentRunModel:
        model = self.get(run_id)
        if model.status in {AgentRunStatus.COMPLETED.value, AgentRunStatus.FAILED.value}:
            raise ConflictError("completed or failed agent runs cannot be cancelled", {"run_id": run_id})
        model.status = AgentRunStatus.CANCELLED.value
        model.completed_at = utcnow()
        model.heartbeat_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def retry(self, run_id: str) -> AgentRunModel:
        model = self.get(run_id)
        if model.status != AgentRunStatus.FAILED.value:
            raise ConflictError("only failed agent runs can be retried", {"run_id": run_id})
        model.status = AgentRunStatus.QUEUED.value
        model.error = None
        model.result = None
        model.started_at = None
        model.completed_at = None
        model.heartbeat_at = None
        self.session.commit()
        self.session.refresh(model)
        return model

    def start_step(
        self,
        *,
        run_id: str,
        campaign_id: str,
        phase: str,
        sequence: int,
        objective: str,
        input_snapshot: dict[str, Any],
    ) -> AgentStepModel:
        self.heartbeat(run_id, phase=phase)
        model = AgentStepModel(
            id=new_id("agent_step"),
            run_id=run_id,
            campaign_id=campaign_id,
            phase=phase,
            status=AgentStepStatus.RUNNING.value,
            sequence=sequence,
            objective=objective,
            input_snapshot=input_snapshot,
            output_snapshot=None,
            observation=None,
            error=None,
            started_at=utcnow(),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def complete_step(
        self,
        step_id: str,
        *,
        output_snapshot: dict[str, Any] | None = None,
        observation: dict[str, Any] | None = None,
    ) -> AgentStepModel:
        model = self._get_step(step_id)
        model.status = AgentStepStatus.COMPLETED.value
        model.output_snapshot = output_snapshot
        model.observation = observation
        model.error = None
        model.completed_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def fail_step(self, step_id: str, error: str) -> AgentStepModel:
        model = self._get_step(step_id)
        model.status = AgentStepStatus.FAILED.value
        model.error = error
        model.completed_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def start_tool_call(
        self,
        *,
        run_id: str,
        campaign_id: str,
        tool_name: str,
        args: dict[str, Any],
        step_id: str | None = None,
        reason: str | None = None,
    ) -> ToolCallModel:
        run = self.get(run_id)
        if run.tool_call_count >= run.max_tool_calls:
            raise ConflictError("agent run exceeded max tool calls", {"run_id": run_id})
        run.tool_call_count += 1
        run.heartbeat_at = utcnow()
        model = ToolCallModel(
            id=new_id("tool_call"),
            run_id=run_id,
            step_id=step_id,
            campaign_id=campaign_id,
            tool_name=tool_name,
            status=ToolCallStatus.RUNNING.value,
            reason=reason,
            args=args,
            observation=None,
            error=None,
            started_at=utcnow(),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def complete_tool_call(self, tool_call_id: str, observation: Any) -> ToolCallModel:
        model = self._get_tool_call(tool_call_id)
        model.status = ToolCallStatus.COMPLETED.value
        model.observation = observation
        model.error = None
        model.completed_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def fail_tool_call(self, tool_call_id: str, error: str) -> ToolCallModel:
        model = self._get_tool_call(tool_call_id)
        model.status = ToolCallStatus.FAILED.value
        model.error = error
        model.completed_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def _get_step(self, step_id: str) -> AgentStepModel:
        model = self.session.get(AgentStepModel, step_id)
        if model is None:
            raise NotFoundError("agent step not found", {"step_id": step_id})
        return model

    def _get_tool_call(self, tool_call_id: str) -> ToolCallModel:
        model = self.session.get(ToolCallModel, tool_call_id)
        if model is None:
            raise NotFoundError("tool call not found", {"tool_call_id": tool_call_id})
        return model
