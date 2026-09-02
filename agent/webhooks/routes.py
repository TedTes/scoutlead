from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AppServices, DbSession, get_services
from webhooks.schemas import WebhookDeliveryCreate, WebhookDeliveryRead
from webhooks.service import WebhookDeliveryService

router = APIRouter(tags=["webhooks"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> WebhookDeliveryService:
    return WebhookDeliveryService(
        session,
        timeout_seconds=services.settings.request_timeout_seconds,
    )


@router.get("/discovery-runs/{run_id}/webhook-deliveries", response_model=list[WebhookDeliveryRead])
def list_webhook_deliveries(
    run_id: str,
    service: Annotated[WebhookDeliveryService, Depends(_service)],
):
    return service.list_by_campaign(run_id)


@router.post("/discovery-runs/{run_id}/webhook-deliveries", response_model=WebhookDeliveryRead)
def send_approved_shortlist_webhook(
    run_id: str,
    request: WebhookDeliveryCreate,
    service: Annotated[WebhookDeliveryService, Depends(_service)],
):
    return service.send_approved_shortlist(run_id, request)
