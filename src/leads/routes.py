from fastapi import APIRouter

from app.dependencies import DbSession
from leads.repository import LeadRepository
from leads.schemas import LeadRead

router = APIRouter(tags=["leads"])


@router.get("/campaigns/{campaign_id}/leads", response_model=list[LeadRead])
def list_campaign_leads(campaign_id: str, session: DbSession):
    return LeadRepository(session).list_by_campaign(campaign_id)


@router.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: str, session: DbSession):
    return LeadRepository(session).get(lead_id)
