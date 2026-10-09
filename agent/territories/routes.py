from datetime import datetime

from fastapi import APIRouter, Response, status
from sqlalchemy import and_, select

from audience_runs.schemas import AudienceRunState
from audience_runs.service import AudienceRunService
from app.dependencies import CurrentAuth, DbSession
from db.models import (
    AudienceRunModel,
    LeadModel,
    ProfileDeliveryItemModel,
    QueueJobModel,
    TerritoryDeliveryModel,
)
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from leads.schemas import LeadRead
from leads.export import leads_csv
from shared.utils import utcnow
from territories.metrics import (
    TerritoryMetricsRead,
    TerritoryMetricsService,
    territory_metrics_csv,
)
from territories.changes import ProfileChangeService, ProfileFactChangeRead
from territories.schemas import (
    ProfileBatchRead,
    ProfileBatchState,
    ProfileCreate,
    ProfileOptionsRead,
    ProfileQueuedRead,
    TerritoryCreate,
    TerritoryDeliveryRead,
    TerritoryMinFit,
    TerritoryRead,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryUpdate,
)
from territories.refresh import eligible_delivery_leads
from territories.service import TerritoryService


router = APIRouter(prefix="/territories", tags=["territories"])
profiles_router = APIRouter(prefix="/profiles", tags=["profiles"])


def _service(session: DbSession, auth: CurrentAuth) -> TerritoryService:
    return TerritoryService(session, workspace_id=auth.workspace_id)


@router.post("/resolve", response_model=TerritoryResolutionRead)
def resolve_territory(
    request: TerritoryResolveRequest,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(session, auth).resolve(request)


@router.post("", response_model=TerritoryRead, status_code=status.HTTP_201_CREATED)
def create_territory(data: TerritoryCreate, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).create(data)


@router.get("", response_model=list[TerritoryRead])
def list_territories(session: DbSession, auth: CurrentAuth):
    return _service(session, auth).list()


@router.get("/{territory_id}", response_model=TerritoryRead)
def get_territory(territory_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).get(territory_id)


@router.patch("/{territory_id}", response_model=TerritoryRead)
def update_territory(
    territory_id: str,
    update: TerritoryUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(session, auth).update(territory_id, update)


@router.delete("/{territory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_territory(territory_id: str, session: DbSession, auth: CurrentAuth):
    _service(session, auth).delete(territory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{territory_id}/deliveries", response_model=list[TerritoryDeliveryRead])
def list_territory_deliveries(territory_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).list_deliveries(territory_id)


@router.get("/{territory_id}/metrics", response_model=TerritoryMetricsRead)
def territory_metrics(
    territory_id: str,
    session: DbSession,
    auth: CurrentAuth,
    weeks: int = 8,
):
    return TerritoryMetricsService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).calculate(territory_id, weeks=max(1, min(52, weeks)))


@router.get("/{territory_id}/metrics.csv")
def export_territory_metrics(
    territory_id: str,
    session: DbSession,
    auth: CurrentAuth,
    weeks: int = 8,
):
    metrics = TerritoryMetricsService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).calculate(territory_id, weeks=max(1, min(52, weeks)))
    return Response(
        content=territory_metrics_csv(metrics),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{territory_id}-metrics.csv"'
        },
    )


@router.post(
    "/{territory_id}/refresh",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def refresh_territory(
    territory_id: str,
    session: DbSession,
    auth: CurrentAuth,
):
    service = _service(session, auth)
    territory = service.get(territory_id)
    job = QueueService(session).enqueue_territory_refresh(
        territory.id,
        utcnow().replace(microsecond=0).isoformat(),
        criteria_version=territory.criteria_version,
    )
    return ProfileQueuedRead(profile=service.get_read(territory.id), job=job)


@router.get(
    "/{territory_id}/deliveries/{delivery_id}/contacts",
    response_model=list[LeadRead],
)
def list_delivery_contacts(
    territory_id: str,
    delivery_id: str,
    session: DbSession,
    auth: CurrentAuth,
):
    territory_service = _service(session, auth)
    territory = territory_service.get(territory_id)
    delivery = territory_service.territories.get_delivery(territory_id, delivery_id)
    if delivery.viewed_at is None:
        delivery.viewed_at = utcnow()
        session.commit()
    return _delivery_contacts(
        session,
        campaign_id=delivery.campaign_id,
        min_fit=TerritoryMinFit(territory.min_fit),
    )


@router.get("/{territory_id}/deliveries/{delivery_id}/export.csv")
def export_delivery_contacts(
    territory_id: str,
    delivery_id: str,
    session: DbSession,
    auth: CurrentAuth,
):
    territory_service = _service(session, auth)
    territory = territory_service.get(territory_id)
    delivery = territory_service.territories.get_delivery(territory_id, delivery_id)
    contacts = _delivery_contacts(
        session,
        campaign_id=delivery.campaign_id,
        min_fit=TerritoryMinFit(territory.min_fit),
    )
    return Response(
        content=leads_csv(
            contacts,
            scoutlead_path=f"/territories/{territory_id}/deliveries/{delivery_id}",
        ),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{territory_id}-{delivery_id}.csv"'
        },
    )


@profiles_router.post(
    "",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_profile(data: ProfileCreate, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.create_profile(data, commit=False)
    run = AudienceRunService(session, workspace_id=auth.workspace_id).create(
        profile.id,
        commit=False,
    )
    job = QueueService(session).enqueue_audience_run(run.id, commit=False)
    session.commit()
    session.refresh(job)
    return ProfileQueuedRead(profile=service.get_read(profile.id), job=job)


@profiles_router.get("", response_model=list[TerritoryRead])
def list_profiles(session: DbSession, auth: CurrentAuth):
    return _service(session, auth).list()


@profiles_router.get("/options", response_model=ProfileOptionsRead)
def profile_options(session: DbSession, auth: CurrentAuth):
    return ProfileOptionsRead(
        business_types=_service(session, auth).profile_options(),
    )


@profiles_router.get("/{profile_id}", response_model=TerritoryRead)
def get_profile(profile_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).get_read(profile_id)


@profiles_router.get(
    "/{profile_id}/changes",
    response_model=list[ProfileFactChangeRead],
)
def list_profile_changes(
    profile_id: str,
    session: DbSession,
    auth: CurrentAuth,
    since: datetime | None = None,
    limit: int = 100,
):
    return ProfileChangeService(
        session,
        workspace_id=auth.workspace_id,
    ).list(profile_id, since=since, limit=limit)


@profiles_router.patch("/{profile_id}", response_model=TerritoryRead)
def update_profile(
    profile_id: str,
    update: TerritoryUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    service = _service(session, auth)
    service.update(profile_id, update)
    return service.get_read(profile_id)


@profiles_router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(profile_id: str, session: DbSession, auth: CurrentAuth):
    _service(session, auth).delete(profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@profiles_router.post(
    "/{profile_id}/refill",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def refill_profile(profile_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(profile_id)
    run = AudienceRunService(session, workspace_id=auth.workspace_id).create(
        profile.id,
        commit=False,
    )
    job = QueueService(session).enqueue_audience_run(run.id, commit=False)
    session.commit()
    session.refresh(job)
    return ProfileQueuedRead(profile=service.get_read(profile.id), job=job)


@profiles_router.get("/{profile_id}/current-batch", response_model=ProfileBatchRead)
def current_profile_batch(profile_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(profile_id)
    run_service = AudienceRunService(session, workspace_id=auth.workspace_id)
    latest_run = session.scalar(
        select(AudienceRunModel)
        .where(AudienceRunModel.audience_id == profile.id)
        .order_by(AudienceRunModel.created_at.desc())
        .limit(1)
    )
    latest_job = _latest_profile_job(
        session,
        latest_run.id if latest_run is not None else None,
    )
    active_job = (
        latest_job
        if latest_job is not None
        and latest_job.status in {JobStatus.QUEUED.value, JobStatus.RUNNING.value}
        else None
    )
    leads = run_service.latest_leads_for_audience(profile.id)
    remaining = sum(
        not lead.shortlisted_at
        and not lead.last_contacted_at
        and lead.review_status.value != "not_fit"
        for lead in leads
    )
    if active_job is not None and (
        active_job.attempts > 1
        or (
            active_job.status == JobStatus.QUEUED.value
            and active_job.attempts > 0
        )
    ):
        state = ProfileBatchState.RETRYING
    elif active_job is not None:
        state = ProfileBatchState.SCORING
    elif latest_job is not None and latest_job.status in {
        JobStatus.FAILED.value,
        JobStatus.DEAD_LETTER.value,
    }:
        state = ProfileBatchState.FAILED
    elif latest_run is None:
        state = ProfileBatchState.SETUP
    elif latest_run.state == AudienceRunState.FAILED.value:
        state = ProfileBatchState.FAILED
    elif latest_run.state == AudienceRunState.READY.value:
        state = ProfileBatchState.READY if leads else ProfileBatchState.EMPTY
    elif latest_run.state == AudienceRunState.PARTIAL.value:
        state = ProfileBatchState.PARTIAL if leads else ProfileBatchState.EMPTY
    else:
        state = ProfileBatchState.SCORING
    return ProfileBatchRead(
        profile=service.get_read(profile.id),
        delivery=None,
        audience_run_id=latest_run.id if latest_run is not None else None,
        outreach_campaign_id=(
            latest_run.outreach_campaign_id if latest_run is not None else None
        ),
        leads=leads,
        state=state,
        requested_count=profile.batch_size,
        result_count=len(leads),
        remaining_count=remaining,
        failure_class=(
            _failure_class(
                latest_job.last_error
                if latest_job is not None and latest_job.last_error
                else latest_run.failure_reason if latest_run is not None else None
            )
            if state in {ProfileBatchState.RETRYING, ProfileBatchState.FAILED}
            else None
        ),
        retry_at=(
            active_job.run_after
            if state == ProfileBatchState.RETRYING and active_job is not None
            else None
        ),
    )


def _latest_profile_job(
    session: DbSession,
    audience_run_id: str | None,
) -> QueueJobModel | None:
    if audience_run_id is None:
        return None
    jobs = list(
        session.scalars(
            select(QueueJobModel)
            .where(
                QueueJobModel.type == JobType.AUDIENCE_RUN.value,
            )
            .order_by(QueueJobModel.created_at.desc())
        )
    )
    return next(
        (
            job
            for job in jobs
            if job.payload.get("audience_run_id") == audience_run_id
        ),
        None,
    )


def _failure_class(error: str | None) -> str:
    normalized = str(error or "").lower()
    if "insufficient_quota" in normalized or "quota" in normalized:
        return "quota"
    if "429" in normalized or "rate limit" in normalized or "rate_limit" in normalized:
        return "rate_limit"
    return "other"


def _delivery_contacts(
    session: DbSession,
    *,
    campaign_id: str,
    min_fit: TerritoryMinFit,
) -> list[LeadRead]:
    leads = list(
        session.scalars(select(LeadModel).where(LeadModel.campaign_id == campaign_id))
    )
    return eligible_delivery_leads(leads, min_fit=min_fit)
