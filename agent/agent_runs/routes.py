from fastapi import APIRouter

from agent_runs.schemas import AgentRunCreate, AgentRunDetail, AgentRunRead, CampaignTrace
from agent_runs.service import AgentRunService
from app.dependencies import CurrentAuth, DbSession
from campaigns.repository import CampaignRepository
from db.models import AgentRunModel
from shared.errors import NotFoundError

router = APIRouter(tags=["agent-runs"])


@router.post("/agent-runs", response_model=AgentRunRead)
def create_agent_run(request: AgentRunCreate, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(request.campaign_id)
    return AgentRunService(session).create(request)


@router.get("/agent-runs", response_model=list[AgentRunRead])
def list_agent_runs(session: DbSession, auth: CurrentAuth):
    runs = AgentRunService(session).list()
    if not auth.workspace_id:
        return runs
    campaign_ids = {run.campaign_id for run in runs}
    allowed_ids = {
        campaign_id
        for campaign_id in campaign_ids
        if _campaign_in_scope(campaign_id, session, auth)
    }
    return [run for run in runs if run.campaign_id in allowed_ids]


@router.get("/campaigns/{campaign_id}/agent-runs", response_model=list[AgentRunRead])
def list_campaign_agent_runs(campaign_id: str, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return AgentRunService(session).list_by_campaign(campaign_id)


@router.get("/campaigns/{campaign_id}/trace", response_model=CampaignTrace)
def get_campaign_trace(campaign_id: str, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return AgentRunService(session).trace_by_campaign(campaign_id)


@router.get("/agent-runs/{run_id}", response_model=AgentRunDetail)
def get_agent_run(run_id: str, session: DbSession, auth: CurrentAuth):
    _assert_agent_run_in_scope(run_id, session, auth)
    return AgentRunService(session).get(run_id)


@router.get("/agent-runs/{run_id}/trace", response_model=AgentRunDetail)
def get_agent_run_trace(run_id: str, session: DbSession, auth: CurrentAuth):
    _assert_agent_run_in_scope(run_id, session, auth)
    return AgentRunService(session).get(run_id)


@router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunRead)
def cancel_agent_run(run_id: str, session: DbSession, auth: CurrentAuth):
    _assert_agent_run_in_scope(run_id, session, auth)
    return AgentRunService(session).cancel(run_id)


@router.post("/agent-runs/{run_id}/retry", response_model=AgentRunRead)
def retry_agent_run(run_id: str, session: DbSession, auth: CurrentAuth):
    _assert_agent_run_in_scope(run_id, session, auth)
    return AgentRunService(session).retry(run_id)


def _assert_agent_run_in_scope(run_id: str, session: DbSession, auth: CurrentAuth) -> None:
    run = session.get(AgentRunModel, run_id)
    if run is None:
        raise NotFoundError("agent run not found", {"run_id": run_id})
    CampaignRepository(session, workspace_id=auth.workspace_id).get(run.campaign_id)


def _campaign_in_scope(campaign_id: str, session: DbSession, auth: CurrentAuth) -> bool:
    try:
        CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
        return True
    except NotFoundError:
        return False
