from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import Settings


JWKS_PATH = "/.well-known/jwks.json"
logger = logging.getLogger(__name__)


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
        raw_issuer = _clean_endpoint(settings.clerk_jwt_issuer)
        explicit_jwks_url = _normalize_jwks_url(settings.clerk_jwks_url)
        issuer = _strip_jwks_path(raw_issuer)
        issuer_jwks_url = _normalize_jwks_url(raw_issuer) if raw_issuer != issuer else ""
        if issuer and not issuer_jwks_url:
            issuer_jwks_url = f"{issuer}{JWKS_PATH}"

        self.issuer = issuer
        self.jwks_urls = _unique_nonempty([explicit_jwks_url, issuer_jwks_url])
        self.jwks_url = self.jwks_urls[0] if self.jwks_urls else ""
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
        if not self.jwks_urls:
            raise AuthConfigurationError("CLERK_JWKS_URL or CLERK_JWT_ISSUER is required")

        attempted: list[str] = []
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=10) as client:
            for jwks_url in self.jwks_urls:
                attempted.append(_describe_endpoint(jwks_url))
                try:
                    response = await client.get(jwks_url)
                    response.raise_for_status()
                    payload = response.json()
                    keys = payload.get("keys")
                    if not isinstance(keys, list):
                        raise AuthConfigurationError("Clerk JWKS response did not include keys")
                except (httpx.HTTPError, json.JSONDecodeError, AuthConfigurationError) as exc:
                    last_error = exc
                    logger.warning("Could not load Clerk JWKS from %s", attempted[-1])
                    continue

                self.jwks_url = jwks_url
                self._jwks = [dict(key) for key in keys if isinstance(key, dict)]
                self._jwks_expires_at = time.time() + self.cache_ttl_seconds
                return self._jwks

        raise AuthConfigurationError(
            f"could not load Clerk JWKS from {', '.join(attempted)}"
        ) from last_error

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
    try:
        return f"{parts[0]}.{parts[1]}".encode("ascii"), _base64url_decode(parts[2])
    except (binascii.Error, ValueError) as exc:
        raise AuthError("invalid Clerk token") from exc


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


def _clean_endpoint(value: str | None) -> str:
    normalized = (value or "").strip().strip("\"'")
    prefix, separator, endpoint = normalized.partition("=")
    if separator and _looks_like_env_name(prefix):
        normalized = endpoint.strip().strip("\"'")
    normalized = _unwrap_markdown_link(normalized)
    return normalized.rstrip("/").rstrip(",")


def _normalize_jwks_url(value: str | None) -> str:
    normalized = _clean_endpoint(value)
    if not normalized:
        return ""
    duplicate = f"{JWKS_PATH}{JWKS_PATH}"
    while normalized.endswith(duplicate):
        normalized = normalized[: -len(JWKS_PATH)]
    if not normalized.endswith(JWKS_PATH):
        normalized = f"{normalized}{JWKS_PATH}"
    return normalized


def _strip_jwks_path(value: str) -> str:
    normalized = value
    while normalized.endswith(JWKS_PATH):
        normalized = normalized[: -len(JWKS_PATH)].rstrip("/")
    return normalized


def _unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _describe_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _looks_like_env_name(value: str) -> bool:
    normalized = value.strip()
    return bool(normalized) and normalized.upper() == normalized and normalized.replace("_", "").isalnum()


def _unwrap_markdown_link(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("[") and "](" in normalized and normalized.endswith(")"):
        link_target = normalized.rsplit("](", 1)[1][:-1].strip()
        if link_target.startswith(("http://", "https://")):
            return link_target
    return normalized
