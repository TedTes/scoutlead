from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from campaigns.repository import CampaignRepository
from insights.schemas import CampaignInsightRead
from insights.service import CampaignInsightService

router = APIRouter(tags=["insights"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
) -> CampaignInsightService:
    return CampaignInsightService(session=session, llm=services.llm, workspace_id=auth.workspace_id)


@router.get("/campaigns/{campaign_id}/insights", response_model=CampaignInsightRead)
def get_campaign_insights(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return _service(session, services, auth).latest(campaign_id)


@router.post("/campaigns/{campaign_id}/insights", response_model=CampaignInsightRead)
def generate_campaign_insights(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return _service(session, services, auth).generate(campaign_id)
