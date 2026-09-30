from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from app.service_factory import territory_refresh_service
from leads.schemas import LeadRead
from leads.export import leads_csv
from shared.utils import utcnow
from territories.metrics import (
    TerritoryMetricsRead,
    TerritoryMetricsService,
    territory_metrics_csv,
)
from territories.schemas import (
    TerritoryCreate,
    TerritoryDeliveryRead,
    TerritoryMinFit,
    TerritoryRead,
    TerritoryResolveRequest,
    TerritoryResolutionRead,
    TerritoryUpdate,
)
from territories.service import TerritoryService


router = APIRouter(prefix="/territories", tags=["territories"])


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


@router.post("/{territory_id}/refresh", response_model=TerritoryDeliveryRead)
def refresh_territory(
    territory_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    territory = _service(session, auth).get(territory_id)
    return territory_refresh_service(
        session=session,
        services=services,
        workspace_id=territory.workspace_id,
    ).refresh(territory_id)


@router.get(
    "/{territory_id}/deliveries/{delivery_id}/contacts",
    response_model=list[LeadRead],
)
def list_delivery_contacts(
    territory_id: str,
    delivery_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    territory_service = _service(session, auth)
    territory = territory_service.get(territory_id)
    delivery = territory_service.territories.get_delivery(territory_id, delivery_id)
    if delivery.viewed_at is None:
        delivery.viewed_at = utcnow()
        session.commit()
    return territory_refresh_service(
        session=session,
        services=services,
        workspace_id=territory.workspace_id,
    ).contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))


@router.get("/{territory_id}/deliveries/{delivery_id}/export.csv")
def export_delivery_contacts(
    territory_id: str,
    delivery_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    territory_service = _service(session, auth)
    territory = territory_service.get(territory_id)
    delivery = territory_service.territories.get_delivery(territory_id, delivery_id)
    contacts = territory_refresh_service(
        session=session,
        services=services,
        workspace_id=territory.workspace_id,
    ).contacts(delivery, min_fit=TerritoryMinFit(territory.min_fit))
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
