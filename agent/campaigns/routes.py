from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import AppServices, DbSession, get_services
from campaigns.schemas import CampaignCreate, CampaignRead, CampaignRunSummary
from campaigns.service import CampaignService
from evaluation.schemas import CampaignMetrics
from queue.schemas import QueueJobRead
from queue.service import QueueService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def _service(session: DbSession, services: Annotated[AppServices, Depends(get_services)]) -> CampaignService:
    return CampaignService(
        session=session,
        llm=services.llm,
        search_tool=services.search,
        browser=services.browser,
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
    return _service(session, services).run_campaign(campaign_id)


@router.post("/{campaign_id}/enqueue", response_model=QueueJobRead)
def enqueue_campaign_run(campaign_id: str, session: DbSession):
    return QueueService(session).enqueue_campaign_run(campaign_id)


@router.get("/{campaign_id}/metrics", response_model=CampaignMetrics)
def campaign_metrics(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).metrics(campaign_id)
