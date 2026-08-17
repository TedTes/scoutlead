from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel

from leads.schemas import LeadRead
from messages.schemas import MessageRead
from messages.state import assert_send_allowed
from products.schemas import ProductRead
from shared.errors import ConfigurationError, ValidationError
from shared.utils import utcnow


class SendEmailResult(BaseModel):
    provider_message_id: str
    sent_at: str


class EmailToolProtocol(Protocol):
    def send(self, *, product: ProductRead, lead: LeadRead, message: MessageRead) -> SendEmailResult:
        raise NotImplementedError


class EmailTool:
    def __init__(
        self,
        *,
        provider: str = "console",
        endpoint: str | None = None,
        api_key: str | None = None,
        resend_api_key: str | None = None,
        from_address: str | None = None,
        from_name: str = "Soutlead",
        reply_to: str | None = None,
        timeout_seconds: float = 20.0,
        allow_console: bool = True,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.api_key = api_key
        self.resend_api_key = resend_api_key
        self.from_address = from_address
        self.from_name = from_name
        self.reply_to = reply_to
        self.timeout_seconds = timeout_seconds
        self.allow_console = allow_console

    @property
    def is_configured(self) -> bool:
        if self.provider == "console":
            return self.allow_console
        if self.provider == "http":
            return bool(self.endpoint)
        if self.provider == "resend":
            return bool(self.resend_api_key and self.from_address)
        return False

    def send(self, *, product: ProductRead, lead: LeadRead, message: MessageRead) -> SendEmailResult:
        assert_send_allowed(message.status)
        if not lead.contact_email:
            raise ValidationError("lead must have a contact email before outbound sending", {"lead_id": lead.id})

        if self.provider == "console":
            if not self.allow_console:
                raise ConfigurationError("console email provider is disabled for this environment")
            return SendEmailResult(
                provider_message_id=f"console:{message.id}",
                sent_at=utcnow().isoformat(),
            )

        if self.provider == "resend":
            return self._send_resend(product=product, lead=lead, message=message)

        if self.provider != "http":
            raise ConfigurationError("unknown email provider", {"provider": self.provider})

        if self.endpoint is None:
            raise ConfigurationError("HTTP email provider endpoint is required")

        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            headers=headers,
            timeout=self.timeout_seconds,
            json={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
                "message": message.model_dump(mode="json"),
            },
        )
        response.raise_for_status()
        return SendEmailResult.model_validate(response.json())

    def _send_resend(
        self,
        *,
        product: ProductRead,
        lead: LeadRead,
        message: MessageRead,
    ) -> SendEmailResult:
        if not self.resend_api_key or not self.from_address:
            raise ConfigurationError(
                "Resend email provider requires RESEND_API_KEY and EMAIL_FROM_ADDRESS"
            )

        payload: dict[str, object] = {
            "from": f"{self.from_name} <{self.from_address}>",
            "to": [lead.contact_email],
            "subject": message.subject or f"{product.product_name} question for {lead.company_name}",
            "text": message.body,
            "tags": [
                {"name": "product_id", "value": product.id},
                {"name": "campaign_id", "value": message.campaign_id},
                {"name": "lead_id", "value": lead.id},
                {"name": "message_id", "value": message.id},
            ],
        }
        if self.reply_to:
            payload["reply_to"] = self.reply_to

        response = httpx.post(
            str(self.endpoint or "https://api.resend.com/emails"),
            headers={
                "authorization": f"Bearer {self.resend_api_key}",
                "content-type": "application/json",
                "Idempotency-Key": message.id,
            },
            timeout=self.timeout_seconds,
            json=payload,
        )
        response.raise_for_status()
        payload = response.json()

        return SendEmailResult(
            provider_message_id=f"resend:{payload.get('id', message.id)}",
            sent_at=utcnow().isoformat(),
        )
