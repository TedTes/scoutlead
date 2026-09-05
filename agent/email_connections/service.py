from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import Settings
from email_connections.crypto import TokenCipher
from email_connections.repository import EmailConnectionRepository
from email_connections.schemas import EmailConnectionRead, EmailProvider
from products.repository import ProductRepository
from shared.errors import ConfigurationError, ValidationError


class GmailAuthorizationUrl(BaseModel):
    authorization_url: str


class GmailConnectionStatus(BaseModel):
    product_id: str
    provider: EmailProvider = EmailProvider.GMAIL
    connected: bool
    email_address: str | None = None
    scopes: list[str] = Field(default_factory=list)
    last_error: str | None = None


class GmailOAuthService:
    def __init__(
        self,
        *,
        session: Session,
        settings: Settings,
        workspace_id: str | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.connections = EmailConnectionRepository(session)
        self.products = ProductRepository(session, workspace_id=workspace_id)

    def status(self, product_id: str) -> GmailConnectionStatus:
        self.products.get(product_id)
        connection = self.connections.get_active_for_product(product_id, EmailProvider.GMAIL)
        if connection is None:
            return GmailConnectionStatus(product_id=product_id, connected=False)
        return GmailConnectionStatus(
            product_id=product_id,
            connected=True,
            email_address=connection.email_address,
            scopes=connection.scopes,
            last_error=connection.last_error,
        )

    def authorization_url(self, product_id: str) -> GmailAuthorizationUrl:
        self.products.get(product_id)
        self._assert_oauth_configured()
        state = self._encode_state({"product_id": product_id, "issued_at": int(time.time())})
        params = {
            "client_id": self.settings.google_oauth_client_id,
            "redirect_uri": self.settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.settings.gmail_oauth_scopes),
            "state": state,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
        }
        return GmailAuthorizationUrl(
            authorization_url=f"{self.settings.google_oauth_auth_url}?{urlencode(params)}"
        )

    def complete_oauth(self, *, code: str, state: str) -> EmailConnectionRead:
        payload = self._decode_state(state)
        product_id = str(payload.get("product_id") or "")
        if not product_id:
            raise ValidationError("Gmail OAuth state is missing a product id")
        self.products.get(product_id)
        self._assert_oauth_configured()

        token_payload = self._exchange_code(code)
        refresh_token = str(token_payload.get("refresh_token") or "")
        if not refresh_token:
            existing = self.connections.get_active_for_product(product_id, EmailProvider.GMAIL)
            if existing is None:
                raise ConfigurationError(
                    "Google did not return a Gmail refresh token",
                    {
                        "user_message": (
                            "Reconnect Gmail and approve offline access so ScoutLead can send "
                            "approved messages later."
                        )
                    },
                )
            refresh_token = TokenCipher(self.settings.google_token_encryption_key).decrypt(
                existing.encrypted_refresh_token
            )

        access_token = str(token_payload.get("access_token") or "")
        email_address = self._email_from_token_response(token_payload)
        if not email_address and access_token:
            email_address = self._fetch_userinfo_email(access_token)
        if not email_address:
            raise ConfigurationError(
                "Google did not return an email address for this Gmail connection",
                {"user_message": "Reconnect Gmail and grant the email identity permission."},
            )

        scope_text = str(token_payload.get("scope") or "")
        scopes = scope_text.split() if scope_text else list(self.settings.gmail_oauth_scopes)
        encrypted_refresh_token = TokenCipher(self.settings.google_token_encryption_key).encrypt(
            refresh_token
        )
        connection = self.connections.upsert(
            product_id=product_id,
            provider=EmailProvider.GMAIL,
            email_address=email_address,
            encrypted_refresh_token=encrypted_refresh_token,
            scopes=scopes,
        )
        return EmailConnectionRead.model_validate(connection)

    def disconnect(self, product_id: str) -> GmailConnectionStatus:
        self.products.get(product_id)
        connection = self.connections.get_for_product(product_id, EmailProvider.GMAIL)
        if connection is not None and connection.disconnected_at is None:
            self.connections.disconnect(product_id, EmailProvider.GMAIL)
        return GmailConnectionStatus(product_id=product_id, connected=False)

    def _assert_oauth_configured(self) -> None:
        missing = [
            key
            for key, value in {
                "GOOGLE_OAUTH_CLIENT_ID": self.settings.google_oauth_client_id,
                "GOOGLE_OAUTH_CLIENT_SECRET": self.settings.google_oauth_client_secret,
                "GOOGLE_OAUTH_REDIRECT_URI": self.settings.google_oauth_redirect_uri,
                "GOOGLE_TOKEN_ENCRYPTION_KEY": self.settings.google_token_encryption_key,
            }.items()
            if not value
        ]
        if missing:
            raise ConfigurationError(
                "Gmail OAuth is not configured",
                {
                    "missing": missing,
                    "user_message": "Configure Gmail OAuth before connecting an inbox.",
                },
            )

    def _exchange_code(self, code: str) -> dict[str, Any]:
        response = httpx.post(
            self.settings.google_oauth_token_url,
            headers={"accept": "application/json"},
            data={
                "code": code,
                "client_id": self.settings.google_oauth_client_id,
                "client_secret": self.settings.google_oauth_client_secret,
                "redirect_uri": self.settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=self.settings.request_timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ConfigurationError(
                "Gmail OAuth token exchange failed",
                {
                    "status_code": response.status_code,
                    "response_body": response.text[:1000],
                    "user_message": "Gmail connection failed. Try connecting again.",
                },
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise ConfigurationError("Gmail OAuth token exchange returned an invalid response")
        return data

    def _fetch_userinfo_email(self, access_token: str) -> str | None:
        response = httpx.get(
            self.settings.google_userinfo_url,
            headers={"authorization": f"Bearer {access_token}", "accept": "application/json"},
            timeout=self.settings.request_timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        data = response.json()
        if not isinstance(data, dict):
            return None
        email = data.get("email")
        return str(email) if email else None

    def _email_from_token_response(self, token_payload: dict[str, Any]) -> str | None:
        id_token = token_payload.get("id_token")
        if not isinstance(id_token, str):
            return None
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        try:
            claims = json.loads(_urlsafe_b64decode(parts[1]).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
        email = claims.get("email")
        return str(email) if email else None

    def _encode_state(self, payload: dict[str, Any]) -> str:
        encoded_payload = _urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        signature = _urlsafe_b64encode(
            hmac.new(self._state_secret(), encoded_payload.encode(), hashlib.sha256).digest()
        )
        return f"{encoded_payload}.{signature}"

    def _decode_state(self, state: str) -> dict[str, Any]:
        try:
            encoded_payload, encoded_signature = state.split(".", 1)
        except ValueError as exc:
            raise ValidationError("Gmail OAuth state is invalid") from exc
        expected_signature = _urlsafe_b64encode(
            hmac.new(self._state_secret(), encoded_payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(encoded_signature, expected_signature):
            raise ValidationError("Gmail OAuth state is invalid")
        try:
            payload = json.loads(_urlsafe_b64decode(encoded_payload).decode("utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValidationError("Gmail OAuth state is invalid") from exc
        issued_at = int(payload.get("issued_at") or 0)
        if issued_at < int(time.time()) - 600:
            raise ValidationError("Gmail OAuth state expired")
        if not isinstance(payload, dict):
            raise ValidationError("Gmail OAuth state is invalid")
        return payload

    def _state_secret(self) -> bytes:
        value = (
            self.settings.google_oauth_state_secret
            or self.settings.api_auth_token
            or self.settings.google_token_encryption_key
            or self.settings.google_oauth_client_secret
        )
        if not value:
            raise ConfigurationError("Gmail OAuth state signing is not configured")
        return value.encode("utf-8")


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
