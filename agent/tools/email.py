from __future__ import annotations

import base64
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

import httpx
from pydantic import BaseModel
from sqlalchemy.orm import Session

from email_connections.crypto import TokenCipher
from email_connections.repository import EmailConnectionRepository
from email_connections.schemas import EmailProvider
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
        google_oauth_client_id: str | None = None,
        google_oauth_client_secret: str | None = None,
        google_oauth_token_url: str = "https://oauth2.googleapis.com/token",
        google_token_encryption_key: str | None = None,
        gmail_api_base_url: str = "https://gmail.googleapis.com/gmail/v1",
        timeout_seconds: float = 20.0,
        allow_console: bool = True,
        session: Session | None = None,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.api_key = api_key
        self.resend_api_key = resend_api_key
        self.from_address = from_address
        self.from_name = from_name
        self.reply_to = reply_to
        self.google_oauth_client_id = google_oauth_client_id
        self.google_oauth_client_secret = google_oauth_client_secret
        self.google_oauth_token_url = google_oauth_token_url
        self.google_token_encryption_key = google_token_encryption_key
        self.gmail_api_base_url = gmail_api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.allow_console = allow_console
        self.session = session

    def bind_session(self, session: Session) -> EmailTool:
        return EmailTool(
            provider=self.provider,
            endpoint=self.endpoint,
            api_key=self.api_key,
            resend_api_key=self.resend_api_key,
            from_address=self.from_address,
            from_name=self.from_name,
            reply_to=self.reply_to,
            google_oauth_client_id=self.google_oauth_client_id,
            google_oauth_client_secret=self.google_oauth_client_secret,
            google_oauth_token_url=self.google_oauth_token_url,
            google_token_encryption_key=self.google_token_encryption_key,
            gmail_api_base_url=self.gmail_api_base_url,
            timeout_seconds=self.timeout_seconds,
            allow_console=self.allow_console,
            session=session,
        )

    @property
    def is_configured(self) -> bool:
        if self.provider == "console":
            return self.allow_console
        if self.provider == "http":
            return bool(self.endpoint)
        if self.provider == "resend":
            return bool(self.resend_api_key and self.from_address)
        if self.provider == "gmail":
            return bool(
                self.google_oauth_client_id
                and self.google_oauth_client_secret
                and self.google_token_encryption_key
            )
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

        if self.provider == "gmail":
            return self._send_gmail(product=product, lead=lead, message=message)

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

    def _send_gmail(
        self,
        *,
        product: ProductRead,
        lead: LeadRead,
        message: MessageRead,
    ) -> SendEmailResult:
        if not self.google_oauth_client_id or not self.google_oauth_client_secret:
            raise ConfigurationError(
                "Gmail email provider requires GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET"
            )
        if self.session is None:
            raise ConfigurationError("Gmail email provider requires an active database session")

        connection = EmailConnectionRepository(self.session).get_active_for_product(
            product.id, EmailProvider.GMAIL
        )
        if connection is None or not connection.encrypted_refresh_token:
            raise ConfigurationError(
                "Gmail is not connected for this product",
                {"product_id": product.id, "user_message": "Connect Gmail before sending outreach."},
            )

        repository = EmailConnectionRepository(self.session)
        refresh_token = TokenCipher(self.google_token_encryption_key).decrypt(
            connection.encrypted_refresh_token
        )
        access_token = self._refresh_gmail_access_token(refresh_token)
        mime_message = self._build_gmail_message(
            from_address=connection.email_address,
            to_address=lead.contact_email,
            subject=message.subject or f"{product.product_name} question for {lead.company_name}",
            body=message.body,
            message_id=message.id,
        )
        raw_message = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("ascii")
        response = httpx.post(
            f"{self.gmail_api_base_url}/users/me/messages/send",
            headers={
                "authorization": f"Bearer {access_token}",
                "accept": "application/json",
                "content-type": "application/json",
            },
            timeout=self.timeout_seconds,
            json={"raw": raw_message},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            repository.set_last_error(connection.id, response.text[:1000])
            raise ConfigurationError(
                "Gmail message send failed",
                {
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                    "user_message": "Gmail could not send this message. Check the connection and try again.",
                },
            ) from exc

        repository.set_last_error(connection.id, None)
        payload = response.json()
        provider_id = payload.get("id") if isinstance(payload, dict) else None
        return SendEmailResult(
            provider_message_id=f"gmail:{provider_id or message.id}",
            sent_at=utcnow().isoformat(),
        )

    def _refresh_gmail_access_token(self, refresh_token: str) -> str:
        response = httpx.post(
            self.google_oauth_token_url,
            headers={"accept": "application/json"},
            data={
                "client_id": self.google_oauth_client_id,
                "client_secret": self.google_oauth_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConfigurationError(
                "Gmail access token refresh failed",
                {
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                    "user_message": "Reconnect Gmail before sending outreach.",
                },
            ) from exc
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise ConfigurationError("Gmail token refresh returned an invalid response")
        return str(payload["access_token"])

    def _build_gmail_message(
        self,
        *,
        from_address: str,
        to_address: str | None,
        subject: str,
        body: str,
        message_id: str,
    ) -> EmailMessage:
        if not to_address:
            raise ValidationError("lead must have a contact email before outbound sending")
        email_message = EmailMessage()
        email_message["To"] = to_address
        email_message["From"] = formataddr((self.from_name, from_address))
        email_message["Subject"] = subject
        email_message["X-ScoutLead-Message-Id"] = message_id
        if self.reply_to:
            email_message["Reply-To"] = self.reply_to
        email_message.set_content(body)
        return email_message
