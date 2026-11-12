from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from audience_runs.schemas import AudienceRunState
from audience_runs.service import AudienceRunService
from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from db.models import (
    AudienceRunModel,
)
from shared.errors import ValidationError
from territories.metrics import (
    AudiencePerformanceRead,
    TerritoryMetricsRead,
    TerritoryMetricsService,
    WorkspaceOverviewRead,
    territory_metrics_csv,
)
from leads.workspace import WorkspaceLeadService
from territories.changes import ProfileChangeService, ProfileFactChangeRead
from territories.schemas import (
    AudienceFolderCreate,
    AudienceFolderRead,
    AudienceFolderUpdate,
    ProfileBatchRead,
    ProfileBatchState,
    ProfileCreate,
    ProfileOptionsRead,
    PlaceRead,
    LocationCityRead,
    LocationCountryRead,
    LocationRegionRead,
    ProfileQueuedRead,
    TerritoryCreate,
    TerritoryRead,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryUpdate,
    TradeCatalogCreate,
    TradeCatalogRead,
    TradeCatalogUpdate,
)
from territories.service import TerritoryService
from territories.folders import AudienceFolderService
from territories.location_catalog import cities, countries, regions
from territories.source_expansion import enqueue_profile_source_expansion


audience_router = APIRouter(prefix="/audiences", tags=["audiences"])
audience_folder_router = APIRouter(prefix="/audience-folders", tags=["audience-folders"])


Services = Annotated[AppServices, Depends(get_services)]


@audience_folder_router.get("", response_model=list[AudienceFolderRead])
def list_audience_folders(product_id: str, session: DbSession, auth: CurrentAuth):
    return AudienceFolderService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).list(product_id=product_id)


@audience_folder_router.post(
    "",
    response_model=AudienceFolderRead,
    status_code=status.HTTP_201_CREATED,
)
def create_audience_folder(
    data: AudienceFolderCreate,
    session: DbSession,
    auth: CurrentAuth,
):
    return AudienceFolderService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).create(data)


@audience_folder_router.patch("/{folder_id}", response_model=AudienceFolderRead)
def rename_audience_folder(
    folder_id: str,
    data: AudienceFolderUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return AudienceFolderService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).rename(folder_id, data.name)


@audience_folder_router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_audience_folder(folder_id: str, session: DbSession, auth: CurrentAuth):
    AudienceFolderService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).delete(folder_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    # Register collection targets for Admin without fetching or validating data.
    # The client path only matches records already stored in the database.
    if services is not None:
        enqueue_profile_source_expansion(
            session,
            profile,
            google_places_configured=bool(services.settings.google_places_api_key),
            search_configured=services.search.is_configured,
            openstreetmap_enabled=services.settings.openstreetmap_enabled,
            apify_sources=[
                source
                for source in services.settings.apify_source_configs
                if source.get("api_token")
                and source.get("actor_id")
                and (
                    source.get("input_template")
                    or source.get("search_url_template")
                    or source.get("input_kind")
                )
            ],
            source_recipes=services.settings.source_template_configs,
            enqueue_refresh=False,
        )
    run_service = AudienceRunService(session, workspace_id=auth.workspace_id)
    run = run_service.create(
        profile.id,
        commit=False,
    )
    run_service.process(run.id)
    return ProfileQueuedRead(
        audience=service.get_read(profile.id),
        audience_run_id=run.id,
    )


@audience_router.get("", response_model=list[TerritoryRead])
def list_audiences(session: DbSession, auth: CurrentAuth):
    return _service(session, auth).list()


@audience_router.get("/summary", response_model=list[AudiencePerformanceRead])
def audience_performance_summary(
    session: DbSession,
    auth: CurrentAuth,
    product_id: str | None = None,
):
    return TerritoryMetricsService(
        session,
        workspace_id=auth.workspace_id or "workspace_default",
    ).audience_performance(product_id=product_id)


@audience_router.get("/overview", response_model=WorkspaceOverviewRead)
def workspace_audience_overview(session: DbSession, auth: CurrentAuth):
    workspace_id = auth.workspace_id or "workspace_default"
    return WorkspaceOverviewRead(
        counts=WorkspaceLeadService(session, workspace_id=workspace_id).counts(),
        audiences=TerritoryMetricsService(
            session,
            workspace_id=workspace_id,
        ).audience_performance(),
    )


@audience_router.get("/options", response_model=ProfileOptionsRead)
def audience_options(session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    return ProfileOptionsRead(
        business_types=service.profile_options(),
        services=service.profile_service_options(),
        opportunity_signals=service.profile_signal_options(),
    )


@audience_router.get("/trades", response_model=list[TradeCatalogRead])
def list_trades(session: DbSession, auth: CurrentAuth):
    return _service(session, auth).trade_catalog()


@audience_router.post(
    "/trades",
    response_model=TradeCatalogRead,
    status_code=status.HTTP_201_CREATED,
)
def create_trade(data: TradeCatalogCreate, session: DbSession, auth: CurrentAuth):
    return _service(session, auth).create_trade(data.label)


@audience_router.patch("/trades/{trade_id}", response_model=TradeCatalogRead)
def update_trade(
    trade_id: str,
    data: TradeCatalogUpdate,
    session: DbSession,
    auth: CurrentAuth,
):
    return _service(session, auth).update_trade(
        trade_id,
        active=data.active,
    )


@audience_router.get("/places", response_model=list[PlaceRead])
def search_places(
    q: str,
    session: DbSession,
    auth: CurrentAuth,
    services: Services = None,
):
    query = " ".join(q.split())
    if len(query) < 2:
        return []
    results = _service(session, auth, services).market_geocoder.search(query, limit=5)
    return [
        PlaceRead(
            label=result.label,
            provider=result.provider,
            external_id=result.external_id,
            country_code=result.country_code,
            latitude=result.latitude,
            longitude=result.longitude,
        )
        for result in results
        if not result.country_code or result.country_code in {"ca", "us", "mx"}
    ]


@audience_router.get("/location-catalog/countries", response_model=list[LocationCountryRead])
def location_countries(session: DbSession, auth: CurrentAuth):
    return countries()


@audience_router.get("/location-catalog/regions", response_model=list[LocationRegionRead])
def location_regions(country_code: str, session: DbSession, auth: CurrentAuth):
    return regions(country_code)


@audience_router.get("/location-catalog/cities", response_model=list[LocationCityRead])
def location_cities(
    country_code: str,
    session: DbSession,
    auth: CurrentAuth,
    region_code: str | None = None,
):
    return cities(country_code, region_code)


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
    status_code=status.HTTP_200_OK,
)
def refill_audience(audience_id: str, session: DbSession, auth: CurrentAuth):
    service = _service(session, auth)
    profile = service.get(audience_id)
    run_service = AudienceRunService(session, workspace_id=auth.workspace_id)
    run = run_service.create(
        profile.id,
        commit=False,
    )
    run_service.process(run.id)
    return ProfileQueuedRead(
        audience=service.get_read(profile.id),
        audience_run_id=run.id,
    )


@audience_router.get("/{audience_id}/current-batch", response_model=ProfileBatchRead)
def current_audience_batch(audience_id: str, session: DbSession, auth: CurrentAuth):
    """Return the latest stored match without starting or repairing background work."""
    service = _service(session, auth)
    profile = service.get(audience_id)
    run_service = AudienceRunService(session, workspace_id=auth.workspace_id)
    latest_run = session.scalar(
        select(AudienceRunModel)
        .where(AudienceRunModel.audience_id == profile.id)
        .order_by(AudienceRunModel.created_at.desc())
        .limit(1)
    )
    outreach_run = session.scalar(
        select(AudienceRunModel)
        .where(
            AudienceRunModel.audience_id == profile.id,
            AudienceRunModel.outreach_campaign_id.is_not(None),
        )
        .order_by(AudienceRunModel.created_at.desc())
        .limit(1)
    )
    leads = run_service.latest_leads_for_audience(profile.id)
    remaining = sum(
        not lead.shortlisted_at
        and not lead.last_contacted_at
        and lead.review_status.value != "not_fit"
        for lead in leads
    )
    location_count = max(1, len(profile.locations or []))
    if latest_run is None:
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
        location_count=location_count,
        locations_completed=(location_count if latest_run is not None else 0),
        failure_class=(
            _failure_class(latest_run.failure_reason)
            if state == ProfileBatchState.FAILED and latest_run is not None
            else None
        ),
        retry_at=None,
    )


def _failure_class(error: str | None) -> str:
    normalized = str(error or "").lower()
    if "insufficient_quota" in normalized or "quota" in normalized:
        return "quota"
    if "429" in normalized or "rate limit" in normalized or "rate_limit" in normalized:
        return "rate_limit"
    return "other"
