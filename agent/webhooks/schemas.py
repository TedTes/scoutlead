from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class WebhookDeliveryStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class WebhookDeliveryCreate(BaseModel):
    event: str = "approved_shortlist.ready"


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    campaign_id: str
    event: str
    url: str
    status: WebhookDeliveryStatus
    request_payload: dict[str, Any]
    response_status: int | None = None
    response_body: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
