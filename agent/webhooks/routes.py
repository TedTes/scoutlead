from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from campaigns.repository import CampaignRepository
from webhooks.schemas import WebhookDeliveryCreate, WebhookDeliveryRead
from webhooks.service import WebhookDeliveryService

router = APIRouter(tags=["webhooks"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
) -> WebhookDeliveryService:
    return WebhookDeliveryService(
        session,
        timeout_seconds=services.settings.request_timeout_seconds,
        workspace_id=auth.workspace_id,
    )


@router.get("/discovery-runs/{run_id}/webhook-deliveries", response_model=list[WebhookDeliveryRead])
def list_webhook_deliveries(
    run_id: str,
    session: DbSession,
    auth: CurrentAuth,
    services: Annotated[AppServices, Depends(get_services)],
):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(run_id)
    return _service(session, services, auth).list_by_campaign(run_id)


@router.post("/discovery-runs/{run_id}/webhook-deliveries", response_model=WebhookDeliveryRead)
def send_approved_shortlist_webhook(
    run_id: str,
    request: WebhookDeliveryCreate,
    session: DbSession,
    auth: CurrentAuth,
    services: Annotated[AppServices, Depends(get_services)],
):
    CampaignRepository(session, workspace_id=auth.workspace_id).get(run_id)
    return _service(session, services, auth).send_approved_shortlist(run_id, request)
