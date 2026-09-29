from fastapi import APIRouter

from app.dependencies import CurrentAuth, DbSession
from outcomes.schemas import LeadOutcomeCreate, LeadOutcomeRead
from outcomes.service import OutcomeService


router = APIRouter(tags=["outcomes"])


@router.post("/leads/{lead_id}/outcomes", response_model=LeadOutcomeRead)
def record_lead_outcome(
    lead_id: str,
    outcome: LeadOutcomeCreate,
    session: DbSession,
    auth: CurrentAuth,
):
    return OutcomeService(
        session,
        workspace_id=auth.workspace_id,
        recorded_by=auth.user_id,
    ).record(lead_id, outcome)


@router.get("/leads/{lead_id}/outcomes", response_model=list[LeadOutcomeRead])
def list_lead_outcomes(lead_id: str, session: DbSession, auth: CurrentAuth):
    return OutcomeService(session, workspace_id=auth.workspace_id).list_for_lead(lead_id)
