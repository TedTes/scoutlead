from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel

from leads.schemas import LeadRead
from messages.schemas import MessageRead
from messages.state import assert_send_allowed
from products.schemas import ProductRead
from shared.utils import utcnow


class SendEmailResult(BaseModel):
    provider_message_id: str
    sent_at: str


class EmailToolProtocol(Protocol):
    def send(self, *, product: ProductRead, lead: LeadRead, message: MessageRead) -> SendEmailResult:
        raise NotImplementedError


class EmailTool:
    def __init__(self, *, endpoint: str | None = None, api_key: str | None = None) -> None:
        self.endpoint = endpoint
        self.api_key = api_key

    def send(self, *, product: ProductRead, lead: LeadRead, message: MessageRead) -> SendEmailResult:
        assert_send_allowed(message.status)
        if self.endpoint is None:
            return SendEmailResult(
                provider_message_id=f"console:{message.id}",
                sent_at=utcnow().isoformat(),
            )

        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            headers=headers,
            json={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
                "message": message.model_dump(mode="json"),
            },
        )
        response.raise_for_status()
        return SendEmailResult.model_validate(response.json())
