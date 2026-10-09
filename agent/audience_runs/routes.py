from fastapi import APIRouter, status

from app.dependencies import CurrentAuth, DbSession
from audience_runs.schemas import AudienceLeadRead, AudienceResultUpdate, AudienceRunRead
from audience_runs.outreach import AudienceOutreachService
from audience_runs.service import AudienceRunService
from job_queue.service import QueueService
from leads.schemas import LeadContactPolicyUpdate, LeadRead


router = APIRouter(prefix="/audiences", tags=["audience-runs"])


@router.post(
    "/{audience_id}/runs",
    response_model=AudienceRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_audience_run(audience_id: str, session: DbSession, auth: CurrentAuth):
    service = AudienceRunService(session, workspace_id=auth.workspace_id)
    run = service.create(audience_id)
    QueueService(session).enqueue_audience_run(run.id)
    return service.get_read(run.id)


@router.get("/{audience_id}/runs/latest", response_model=AudienceRunRead | None)
def latest_audience_run(audience_id: str, session: DbSession, auth: CurrentAuth):
    return AudienceRunService(
        session,
        workspace_id=auth.workspace_id,
    ).latest_for_audience(audience_id)


@router.get("/runs/{run_id}", response_model=AudienceRunRead)
def get_audience_run(run_id: str, session: DbSession, auth: CurrentAuth):
    return AudienceRunService(session, workspace_id=auth.workspace_id).get_read(run_id)


@router.patch(
    "/results/{result_id}",
    response_model=AudienceLeadRead,
)
def update_audience_result(
    result_id: str,
    update: AudienceResultUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return AudienceRunService(
        session,
        workspace_id=auth.workspace_id,
    ).update_result(result_id, update)


@router.post(
    "/results/{result_id}/outreach-lead",
    response_model=LeadRead,
)
def promote_audience_result(
    result_id: str,
    session: DbSession,
    auth: CurrentAuth,
):
    return AudienceOutreachService(
        session,
        workspace_id=auth.workspace_id,
    ).promote(result_id)


@router.patch(
    "/results/{result_id}/contact-policy",
    response_model=AudienceLeadRead,
)
def update_audience_result_contact_policy(
    result_id: str,
    update: LeadContactPolicyUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return AudienceRunService(
        session,
        workspace_id=auth.workspace_id,
    ).update_contact_policy(result_id, update)
