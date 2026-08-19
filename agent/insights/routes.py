from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, DbSession, get_services
from insights.schemas import CampaignInsightRead
from insights.service import CampaignInsightService

router = APIRouter(tags=["insights"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> CampaignInsightService:
    return CampaignInsightService(session=session, llm=services.llm)


@router.get("/campaigns/{campaign_id}/insights", response_model=CampaignInsightRead)
def get_campaign_insights(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).latest(campaign_id)


@router.post("/campaigns/{campaign_id}/insights", response_model=CampaignInsightRead)
def generate_campaign_insights(
    campaign_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).generate(campaign_id)
