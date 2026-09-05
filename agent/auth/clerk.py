from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import time
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import Settings


class AuthError(Exception):
    pass


class AuthConfigurationError(AuthError):
    pass


@dataclass(frozen=True)
class ClerkClaims:
    subject: str
    session_id: str | None
    organization_id: str | None
    email: str | None
    claims: dict[str, Any]

    @property
    def workspace_id(self) -> str:
        return self.organization_id or f"user:{self.subject}"


class ClerkTokenVerifier:
    def __init__(self, settings: Settings, *, cache_ttl_seconds: int = 300) -> None:
        self.issuer = (settings.clerk_jwt_issuer or "").rstrip("/")
        self.jwks_url = settings.clerk_jwks_url or (
            f"{self.issuer}/.well-known/jwks.json" if self.issuer else ""
        )
        self.cache_ttl_seconds = cache_ttl_seconds
        self._jwks_expires_at = 0.0
        self._jwks: list[dict[str, Any]] = []

    async def verify_authorization_header(self, value: str | None) -> ClerkClaims:
        token = _bearer_token(value)
        if not token:
            raise AuthError("missing bearer token")
        return await self.verify_token(token)

    async def verify_token(self, token: str) -> ClerkClaims:
        signed_part, signature = _split_token(token)
        header = _decode_token_json(token, 0)
        payload = _decode_token_json(token, 1)

        if header.get("alg") != "RS256":
            raise AuthError("unsupported Clerk token algorithm")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id:
            raise AuthError("Clerk token is missing a key id")

        public_key = await self._public_key(key_id)
        try:
            public_key.verify(signature, signed_part, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as exc:
            raise AuthError("invalid Clerk token signature") from exc

        self._validate_payload(payload)
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthError("Clerk token is missing a subject")

        return ClerkClaims(
            subject=subject,
            session_id=_optional_string(payload.get("sid")),
            organization_id=_optional_string(payload.get("org_id")),
            email=_optional_string(payload.get("email")),
            claims=payload,
        )

    async def _public_key(self, key_id: str):
        jwks = await self._get_jwks()
        key = next((item for item in jwks if item.get("kid") == key_id), None)
        if not key:
            self._jwks_expires_at = 0
            jwks = await self._get_jwks()
            key = next((item for item in jwks if item.get("kid") == key_id), None)
        if not key:
            raise AuthError("Clerk signing key not found")
        if key.get("kty") != "RSA":
            raise AuthError("unsupported Clerk signing key type")

        n = int.from_bytes(_base64url_decode(str(key["n"])), "big")
        e = int.from_bytes(_base64url_decode(str(key["e"])), "big")
        return rsa.RSAPublicNumbers(e=e, n=n).public_key()

    async def _get_jwks(self) -> list[dict[str, Any]]:
        if self._jwks and self._jwks_expires_at > time.time():
            return self._jwks
        if not self.jwks_url:
            raise AuthConfigurationError("CLERK_JWKS_URL or CLERK_JWT_ISSUER is required")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise AuthConfigurationError("could not load Clerk JWKS") from exc
        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise AuthConfigurationError("Clerk JWKS response did not include keys")
        self._jwks = [dict(key) for key in keys if isinstance(key, dict)]
        self._jwks_expires_at = time.time() + self.cache_ttl_seconds
        return self._jwks

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        now = int(time.time())
        leeway = 60
        expires_at = payload.get("exp")
        if isinstance(expires_at, (int, float)) and expires_at < now - leeway:
            raise AuthError("Clerk token is expired")
        not_before = payload.get("nbf")
        if isinstance(not_before, (int, float)) and not_before > now + leeway:
            raise AuthError("Clerk token is not active yet")
        issuer = payload.get("iss")
        if self.issuer and issuer != self.issuer:
            raise AuthError("Clerk token issuer mismatch")


def _bearer_token(value: str | None) -> str:
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _split_token(token: str) -> tuple[bytes, bytes]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("invalid Clerk token")
    return f"{parts[0]}.{parts[1]}".encode("ascii"), _base64url_decode(parts[2])


def _decode_token_json(token: str, index: int) -> dict[str, Any]:
    try:
        payload = json.loads(_base64url_decode(token.split(".")[index]).decode("utf-8"))
    except (IndexError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise AuthError("invalid Clerk token payload") from exc
    if not isinstance(payload, dict):
        raise AuthError("invalid Clerk token payload")
    return payload


def _base64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
