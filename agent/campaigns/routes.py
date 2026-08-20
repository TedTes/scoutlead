from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from agent_runs.schemas import AgentRunCreate, AgentRunRead
from agent_runs.service import AgentRunService
from app.dependencies import AppServices, DbSession, get_services
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignCreate, CampaignPreflightRead, CampaignRead, CampaignRunSummary
from campaigns.service import CampaignService
from evaluation.schemas import CampaignMetrics
from shared.errors import ConflictError

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _service(session: DbSession, services: Annotated[AppServices, Depends(get_services)]) -> CampaignService:
    return CampaignService(
        session=session,
        llm=services.llm,
        search_tool=services.search,
        browser=services.browser,
        email=services.email,
        google_places_api_key=services.settings.google_places_api_key,
        google_places_api_endpoint=services.settings.google_places_api_endpoint,
        timeout_seconds=services.settings.request_timeout_seconds,
    )


@router.post("", response_model=CampaignRead)
def create_campaign(
    campaign: CampaignCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create(campaign)


@router.get("", response_model=list[CampaignRead])
def list_campaigns(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).list()


@router.get("/{campaign_id}", response_model=CampaignRead)
def get_campaign(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).get(campaign_id)


@router.get("/{campaign_id}/sources", response_model=list[CampaignSourceRead])
def list_campaign_sources(campaign_id: str, session: DbSession):
    return CampaignSourceRepository(session).list_by_campaign(campaign_id)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_campaign(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    _service(session, services).delete(campaign_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{campaign_id}/pause", response_model=CampaignRead)
def pause_campaign(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).pause(campaign_id)


@router.post("/{campaign_id}/resume", response_model=CampaignRead)
def resume_campaign(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).resume(campaign_id)


@router.post("/{campaign_id}/run", response_model=CampaignRunSummary)
def run_campaign(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    service = _service(session, services)
    _assert_preflight_ready(service.preflight(campaign_id))
    agent_run = AgentRunService(session).create(AgentRunCreate(campaign_id=campaign_id))
    return service.run_campaign(campaign_id, agent_run_id=agent_run.id)


@router.post("/{campaign_id}/enqueue", response_model=AgentRunRead)
def enqueue_campaign_run(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    service = _service(session, services)
    _assert_preflight_ready(service.preflight(campaign_id))
    return AgentRunService(session).create(AgentRunCreate(campaign_id=campaign_id))


@router.get("/{campaign_id}/preflight", response_model=CampaignPreflightRead)
def campaign_preflight(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).preflight(campaign_id)


@router.get("/{campaign_id}/metrics", response_model=CampaignMetrics)
def campaign_metrics(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).metrics(campaign_id)


def _assert_preflight_ready(preflight: CampaignPreflightRead) -> None:
    if preflight.ready:
        return
    failures = [check for check in preflight.checks if check.required and check.status == "failed"]
    raise ConflictError(
        "campaign cannot run until required integrations are configured",
        {"failures": [failure.model_dump(mode="json") for failure in failures]},
    )
