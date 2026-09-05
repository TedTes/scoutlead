from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from campaigns.repository import CampaignRepository
from campaigns.schemas import LeadSeedInput
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateRead
from leads.repository import LeadRepository
from leads.schemas import LeadContactPolicyUpdate, LeadRead, LeadUpdate
from leads.service import LeadQualificationService

router = APIRouter(tags=["leads"])


@router.get("/campaigns/{campaign_id}/leads", response_model=list[LeadRead])
def list_campaign_leads(campaign_id: str, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return LeadRepository(session, workspace_id=auth.workspace_id).list_by_campaign(campaign_id)


@router.get("/campaigns/{campaign_id}/discovery-candidates", response_model=list[DiscoveryCandidateRead])
def list_campaign_discovery_candidates(campaign_id: str, session: DbSession, auth: CurrentAuth):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    return DiscoveryCandidateRepository(session).list_by_campaign(campaign_id)


@router.post("/campaigns/{campaign_id}/leads/seeds", response_model=list[LeadRead])
def add_campaign_seed_leads(
    campaign_id: str,
    seeds: list[LeadSeedInput],
    session: DbSession,
    auth: CurrentAuth,
):
    campaign = CampaignRepository(session, workspace_id=auth.workspace_id).get(campaign_id)
    leads = LeadRepository(session, workspace_id=auth.workspace_id)
    return [leads.create_from_seed(campaign_id, campaign.product_id, seed) for seed in seeds]


@router.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: str, session: DbSession, auth: CurrentAuth):
    return LeadRepository(session, workspace_id=auth.workspace_id).get(lead_id)


@router.patch("/leads/{lead_id}", response_model=LeadRead)
def update_lead(lead_id: str, update: LeadUpdate, session: DbSession, auth: CurrentAuth):
    return LeadRepository(session, workspace_id=auth.workspace_id).update(lead_id, update)


@router.patch("/leads/{lead_id}/contact-policy", response_model=LeadRead)
def update_lead_contact_policy(
    lead_id: str,
    update: LeadContactPolicyUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return LeadRepository(session, workspace_id=auth.workspace_id).update_contact_policy(lead_id, update)


@router.post("/leads/{lead_id}/qualify", response_model=LeadRead)
def qualify_lead(
    lead_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    LeadRepository(session, workspace_id=auth.workspace_id).get(lead_id)
    return LeadQualificationService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).qualify(lead_id)
