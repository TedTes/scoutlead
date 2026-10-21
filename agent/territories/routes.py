from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from audience_runs.schemas import AudienceRunState
from audience_runs.service import AudienceRunService
from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from db.models import (
    AudienceRunModel,
    QueueJobModel,
)
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from shared.errors import ValidationError
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
    TerritoryRead,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryUpdate,
)
from territories.service import TerritoryService


audience_router = APIRouter(prefix="/audiences", tags=["audiences"])


Services = Annotated[AppServices, Depends(get_services)]


def _service(
    session: DbSession,
    auth: CurrentAuth,
    services: AppServices | None = None,
) -> TerritoryService:
    return TerritoryService(
        session,
        workspace_id=auth.workspace_id,
        market_geocoder=services.market_geocoder if services is not None else None,
    )


@audience_router.post("/resolve", response_model=TerritoryResolutionRead)
def resolve_audience(
    request: TerritoryResolveRequest,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(session, auth).resolve(request)


@audience_router.post(
    "/from-resolution",
    response_model=TerritoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_audience_from_resolution(
    data: TerritoryCreate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services = None,
):
    return _service(session, auth, services).create(data)


@audience_router.get("/{audience_id}/metrics", response_model=TerritoryMetricsRead)
def audience_metrics(
    audience_id: str,
    session: DbSession,
    auth: CurrentAuth,
    weeks: int = 8,
):
    return TerritoryMetricsService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).calculate(audience_id, weeks=max(1, min(52, weeks)))


@audience_router.get("/{audience_id}/metrics.csv")
def export_audience_metrics(
    audience_id: str,
    session: DbSession,
    auth: CurrentAuth,
    weeks: int = 8,
):
    metrics = TerritoryMetricsService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).calculate(audience_id, weeks=max(1, min(52, weeks)))
    return Response(
        content=territory_metrics_csv(metrics),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{audience_id}-metrics.csv"'
        },
    )


@audience_router.post(
    "",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_201_CREATED,
)
def create_audience(
    data: ProfileCreate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services = None,
):
    if not data.services and not data.signals:
        raise ValidationError(
            "at least one service is required",
            {"user_message": "Choose at least one service before creating an audience."},
        )
    service = _service(session, auth, services)
    profile = service.create_profile(data, commit=False)
    run = AudienceRunService(session, workspace_id=auth.workspace_id).create(
        profile.id,
        commit=False,
    )
    job = QueueService(session).enqueue_audience_run(run.id, commit=False)
    session.commit()
    session.refresh(job)
    return ProfileQueuedRead(audience=service.get_read(profile.id), job=job)


@audience_router.get("", response_model=list[TerritoryRead])
def list_audiences(session: DbSession, auth: CurrentAuth):
    return _service(session, auth).list()


@audience_router.get("/options", response_model=ProfileOptionsRead)
def audience_options(session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    return ProfileOptionsRead(
        business_types=service.profile_options(),
        services=service.profile_service_options(),
        opportunity_signals=service.profile_signal_options(),
    )


@audience_router.get("/{audience_id}", response_model=TerritoryRead)
def get_audience(audience_id: str, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).get_read(audience_id)


@audience_router.get(
    "/{audience_id}/changes",
    response_model=list[ProfileFactChangeRead],
)
def list_audience_changes(
    audience_id: str,
    session: DbSession,
    auth: CurrentAuth,
    since: datetime | None = None,
    limit: int = 100,
):
    return ProfileChangeService(
        session,
        workspace_id=auth.workspace_id,
    ).list(audience_id, since=since, limit=limit)


@audience_router.patch("/{audience_id}", response_model=TerritoryRead)
def update_audience(
    audience_id: str,
    update: TerritoryUpdate,
    session: DbSession,
    auth: CurrentAuth,
    services: Services = None,
):
    service = _service(session, auth, services)
    service.update(audience_id, update)
    return service.get_read(audience_id)


@audience_router.delete("/{audience_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audience(audience_id: str, session: DbSession, auth: CurrentAuth):
    _service(session, auth).delete(audience_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@audience_router.post(
    "/{audience_id}/refill",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def refill_audience(audience_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(audience_id)
    run = AudienceRunService(session, workspace_id=auth.workspace_id).create(
        profile.id,
        commit=False,
    )
    job = QueueService(session).enqueue_audience_run(run.id, commit=False)
    session.commit()
    session.refresh(job)
    return ProfileQueuedRead(audience=service.get_read(profile.id), job=job)


@audience_router.get("/{audience_id}/current-batch", response_model=ProfileBatchRead)
def current_audience_batch(audience_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(audience_id)
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
    if latest_run is not None and latest_job is not None:
        is_initial_run = _is_initial_profile_run(session, latest_run)
        run_is_incomplete = latest_run.state not in {
            AudienceRunState.READY.value,
            AudienceRunState.PARTIAL.value,
            AudienceRunState.FAILED.value,
        }
        if is_initial_run and (
            (
                latest_job.status == JobStatus.QUEUED.value
                and latest_run.state != AudienceRunState.WAITING_VALIDATION.value
            )
            or (
                run_is_incomplete
                and latest_run.state != AudienceRunState.WAITING_VALIDATION.value
                and latest_job.status == JobStatus.COMPLETED.value
            )
            or (
                latest_job.status == JobStatus.RUNNING.value
                and latest_run.deadline_at
                <= datetime.now(latest_run.deadline_at.tzinfo)
            )
        ):
            _process_profile_run(
                session,
                run_id=latest_run.id,
                job_id=latest_job.id,
                workspace_id=auth.workspace_id,
            )
            session.refresh(latest_run)
            session.refresh(latest_job)
        elif (
            latest_job.status == JobStatus.RUNNING.value
            and latest_run.deadline_at <= datetime.now(latest_run.deadline_at.tzinfo)
        ):
            _fail_stalled_profile_run(session, latest_run, latest_job)
            session.refresh(latest_run)
            session.refresh(latest_job)
    outreach_run = session.scalar(
        select(AudienceRunModel)
        .where(
            AudienceRunModel.audience_id == profile.id,
            AudienceRunModel.outreach_campaign_id.is_not(None),
        )
        .order_by(AudienceRunModel.created_at.desc())
        .limit(1)
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
        audience=service.get_read(profile.id),
        audience_run_id=latest_run.id if latest_run is not None else None,
        outreach_campaign_id=(
            outreach_run.outreach_campaign_id if outreach_run is not None else None
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


def _process_profile_run(
    session: DbSession,
    *,
    run_id: str,
    job_id: str,
    workspace_id: str | None,
) -> None:
    job = session.scalar(
        select(QueueJobModel)
        .where(QueueJobModel.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None or job.status not in {
        JobStatus.QUEUED.value,
        JobStatus.RUNNING.value,
        JobStatus.COMPLETED.value,
    }:
        return
    job.status = JobStatus.RUNNING.value
    job.attempts += 1
    job.locked_at = datetime.now(timezone.utc)
    session.commit()
    try:
        _, needs_expansion = AudienceRunService(
            session,
            workspace_id=workspace_id,
        ).process(run_id)
    except Exception as exc:
        session.rollback()
        run = session.get(AudienceRunModel, run_id)
        job = session.get(QueueJobModel, job_id)
        now = datetime.now(timezone.utc)
        if run is not None:
            run.state = AudienceRunState.FAILED.value
            run.failure_reason = str(exc)[:2000]
            run.completed_at = now
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.last_error = str(exc)[:2000]
            job.completed_at = now
            job.locked_at = None
        session.commit()
        return
    job = session.get(QueueJobModel, job_id)
    if job is not None:
        if needs_expansion:
            job.status = JobStatus.QUEUED.value
            job.attempts = max(0, job.attempts - 1)
            job.run_after = datetime.now(timezone.utc)
            job.completed_at = None
        else:
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.now(timezone.utc)
        job.locked_at = None
        session.commit()


def _is_initial_profile_run(session: DbSession, run: AudienceRunModel) -> bool:
    previous_completed = session.scalar(
        select(AudienceRunModel.id)
        .where(
            AudienceRunModel.audience_id == run.audience_id,
            AudienceRunModel.id != run.id,
            AudienceRunModel.state.in_(
                [AudienceRunState.READY.value, AudienceRunState.PARTIAL.value]
            ),
        )
        .limit(1)
    )
    return previous_completed is None


def _fail_stalled_profile_run(
    session: DbSession,
    run: AudienceRunModel,
    job: QueueJobModel,
) -> None:
    now = datetime.now(timezone.utc)
    reason = "Audience matching exceeded its execution deadline. Run the audience again."
    run.state = AudienceRunState.FAILED.value
    run.failure_reason = reason
    run.completed_at = now
    job.status = JobStatus.FAILED.value
    job.last_error = reason
    job.completed_at = now
    job.locked_at = None
    session.commit()


def _failure_class(error: str | None) -> str:
    normalized = str(error or "").lower()
    if "insufficient_quota" in normalized or "quota" in normalized:
        return "quota"
    if "429" in normalized or "rate limit" in normalized or "rate_limit" in normalized:
        return "rate_limit"
    return "other"
