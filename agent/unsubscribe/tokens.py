from __future__ import annotations

import base64
import hashlib
import hmac
import json

from pydantic import BaseModel, field_validator

from shared.errors import ValidationError


class UnsubscribeClaims(BaseModel):
    workspace_id: str
    lead_id: str
    email: str

    @field_validator("workspace_id", "lead_id", "email")
    @classmethod
    def require_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized


def sign_unsubscribe_token(claims: UnsubscribeClaims, secret: str) -> str:
    if not secret:
        raise ValidationError("unsubscribe signing secret is not configured")
    payload = json.dumps(
        claims.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    return f"{_encode(payload)}.{_encode(signature)}"


def verify_unsubscribe_token(token: str, secret: str) -> UnsubscribeClaims:
    if not secret:
        raise ValidationError("unsubscribe signing secret is not configured")
    try:
        payload_part, signature_part = token.split(".", 1)
        payload = _decode(payload_part)
        signature = _decode(signature_part)
    except (ValueError, TypeError) as exc:
        raise ValidationError("invalid unsubscribe token") from exc
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValidationError("invalid unsubscribe token")
    try:
        return UnsubscribeClaims.model_validate_json(payload)
    except ValueError as exc:
        raise ValidationError("invalid unsubscribe token") from exc


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")
