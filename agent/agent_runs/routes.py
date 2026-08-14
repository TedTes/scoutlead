from fastapi import APIRouter

from agent_runs.schemas import AgentRunCreate, AgentRunDetail, AgentRunRead
from agent_runs.service import AgentRunService
from app.dependencies import DbSession

router = APIRouter(tags=["agent-runs"])


@router.post("/agent-runs", response_model=AgentRunRead)
def create_agent_run(request: AgentRunCreate, session: DbSession):
    return AgentRunService(session).create(request)


@router.get("/agent-runs", response_model=list[AgentRunRead])
def list_agent_runs(session: DbSession):
    return AgentRunService(session).list()


@router.get("/campaigns/{campaign_id}/agent-runs", response_model=list[AgentRunRead])
def list_campaign_agent_runs(campaign_id: str, session: DbSession):
    return AgentRunService(session).list_by_campaign(campaign_id)


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetail)
def get_agent_run(run_id: str, session: DbSession):
    return AgentRunService(session).get(run_id)


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunRead)
def cancel_agent_run(run_id: str, session: DbSession):
    return AgentRunService(session).cancel(run_id)


@router.post("/agent-runs/{run_id}/retry", response_model=AgentRunRead)
def retry_agent_run(run_id: str, session: DbSession):
    return AgentRunService(session).retry(run_id)
