from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.dependencies import CurrentAuth, DbSession
from db.models import LeadModel, QueueJobModel
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
    scheduled_for = utcnow().replace(microsecond=0).isoformat()
    job = QueueService(session).enqueue_territory_refresh(
        profile.id,
        scheduled_for,
        criteria_version=profile.criteria_version,
        commit=False,
    )
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


@profiles_router.post(
    "/{profile_id}/refill",
    response_model=ProfileQueuedRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def refill_profile(profile_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(profile_id)
    job = QueueService(session).enqueue_territory_refresh(
        profile.id,
        utcnow().replace(microsecond=0).isoformat(),
        criteria_version=profile.criteria_version,
    )
    return ProfileQueuedRead(profile=service.get_read(profile.id), job=job)


@profiles_router.get("/{profile_id}/current-batch", response_model=ProfileBatchRead)
def current_profile_batch(profile_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(profile_id)
    delivery = service.territories.latest_delivery(profile.id)
    active_job = _active_profile_job(session, profile.id)
    leads: list[LeadRead] = []
    if delivery is not None:
        models = list(
            session.scalars(
                select(LeadModel).where(LeadModel.campaign_id == delivery.campaign_id)
            )
        )
        leads = eligible_delivery_leads(
            models,
            min_fit=TerritoryMinFit(profile.min_fit),
        )
    remaining = sum(
        not lead.shortlisted_at
        and not lead.last_contacted_at
        and lead.review_status != "not_fit"
        for lead in leads
    )
    if active_job is not None:
        state = ProfileBatchState.SCORING
    elif delivery is None:
        state = ProfileBatchState.SETUP
    elif delivery.status == "failed":
        state = ProfileBatchState.FAILED
    elif delivery.status == "ready":
        state = ProfileBatchState.READY
    else:
        state = ProfileBatchState.PARTIAL
    return ProfileBatchRead(
        profile=service.get_read(profile.id),
        delivery=delivery,
        leads=leads,
        state=state,
        requested_count=profile.batch_size,
        result_count=len(leads),
        remaining_count=remaining,
    )


def _active_profile_job(session: DbSession, profile_id: str) -> QueueJobModel | None:
    jobs = list(
        session.scalars(
            select(QueueJobModel)
            .where(
                QueueJobModel.type == JobType.TERRITORY_REFRESH.value,
                QueueJobModel.status.in_(
                    [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
                ),
            )
            .order_by(QueueJobModel.created_at.desc())
        )
    )
    return next(
        (job for job in jobs if job.payload.get("territory_id") == profile_id),
        None,
    )


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
