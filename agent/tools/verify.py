from __future__ import annotations

from dataclasses import dataclass, field
import re
from time import perf_counter
from typing import Any, Protocol

import httpx

from tools.base import ToolResult, ToolSlot

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
VERIFICATION_STATUSES = {"valid", "risky", "invalid", "unknown"}
ZEROBOUNCE_VALIDATE_ENDPOINT = "https://api.zerobounce.net/v2/validate"
BOUNCER_VERIFY_ENDPOINT = "https://api.usebouncer.com/v1.1/email/verify"


@dataclass(frozen=True)
class VerificationResult:
    provider: str
    email: str
    status: str
    reason: str
    score: int
    raw: dict[str, Any] = field(default_factory=dict)

    def as_tool_data(self) -> dict[str, Any]:
        status = self.status if self.status in VERIFICATION_STATUSES else "unknown"
        return {
            "email": self.email,
            "status": status,
            "verdict": status,
            "reason": self.reason,
            "score": max(0, min(100, int(self.score))),
            "raw": self.raw,
        }


class EmailVerifier(Protocol):
    provider_id: str

    def verify(self, email: str, context: dict[str, Any]) -> VerificationResult:
        raise NotImplementedError


class SyntaxEmailVerifier:
    provider_id = "syntax"

    def verify(self, email: str, context: dict[str, Any]) -> VerificationResult:
        if not email:
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="unknown",
                reason="No email address found.",
                score=0,
            )
        if EMAIL_RE.match(email):
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="valid",
                reason="Email syntax is valid. Deliverability was not externally checked.",
                score=80,
            )
        return VerificationResult(
            provider=self.provider_id,
            email=email,
            status="invalid",
            reason="Email syntax is invalid.",
            score=20,
        )


class HttpEmailVerifier:
    provider_id = "http"

    def __init__(
        self,
        *,
        endpoint: str | None,
        api_key: str | None,
        timeout_seconds: float,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def verify(self, email: str, context: dict[str, Any]) -> VerificationResult:
        if not self.endpoint:
            raise ValueError("EMAIL_VERIFICATION_ENDPOINT is required when CONTACT_VERIFICATION_PROVIDER=http")
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.endpoint,
            headers=headers,
            timeout=self.timeout_seconds,
            json={
                "email": email,
                "domain": email.split("@", 1)[1] if "@" in email else None,
                "phone": context.get("phone"),
                "lead": context.get("lead"),
            },
        )
        response.raise_for_status()
        return self._normalize_response(email, response.json())

    def _normalize_response(self, email: str, payload: Any) -> VerificationResult:
        data = payload if isinstance(payload, dict) else {}
        raw_status = str(
            data.get("status")
            or data.get("verdict")
            or data.get("result")
            or data.get("deliverability")
            or "unknown"
        ).lower()
        status = raw_status if raw_status in VERIFICATION_STATUSES else "unknown"
        score_value = data.get("score") or data.get("confidence")
        try:
            score = int(score_value)
        except (TypeError, ValueError):
            score = {"valid": 90, "risky": 55, "invalid": 10, "unknown": 30}[status]
        return VerificationResult(
            provider=self.provider_id,
            email=str(data.get("email") or email),
            status=status,
            reason=str(data.get("reason") or data.get("message") or f"Provider returned {status}."),
            score=score,
            raw=data,
        )


class ZeroBounceEmailVerifier:
    provider_id = "zerobounce"

    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: str | None = None,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or ZEROBOUNCE_VALIDATE_ENDPOINT
        self.timeout_seconds = timeout_seconds

    def verify(self, email: str, context: dict[str, Any]) -> VerificationResult:
        if not self.api_key:
            raise ValueError("ZEROBOUNCE_API_KEY is required when CONTACT_VERIFICATION_PROVIDER=zerobounce")
        if not email:
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="unknown",
                reason="No email address found.",
                score=0,
            )
        if not EMAIL_RE.match(email):
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="invalid",
                reason="Email syntax is invalid. ZeroBounce was not called.",
                score=20,
            )

        params = {
            "api_key": self.api_key,
            "email": email,
        }
        ip_address = str(context.get("ip_address") or context.get("ip") or "").strip()
        if ip_address:
            params["ip_address"] = ip_address
        response = httpx.get(self.endpoint, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("ZeroBounce returned a non-object response")
        if payload.get("error"):
            raise ValueError(f"ZeroBounce verification failed: {payload['error']}")
        return self._normalize_response(email, payload)

    def _normalize_response(self, email: str, payload: dict[str, Any]) -> VerificationResult:
        raw_status = str(payload.get("status") or "unknown").lower().strip()
        sub_status = str(payload.get("sub_status") or "").lower().strip()
        status, score = _zerobounce_status(raw_status, sub_status, payload)
        return VerificationResult(
            provider=self.provider_id,
            email=str(payload.get("address") or email),
            status=status,
            reason=_zerobounce_reason(raw_status, sub_status, payload),
            score=score,
            raw=payload,
        )


class BouncerEmailVerifier:
    provider_id = "bouncer"

    def __init__(
        self,
        *,
        api_key: str | None,
        endpoint: str | None = None,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or BOUNCER_VERIFY_ENDPOINT
        self.timeout_seconds = timeout_seconds

    def verify(self, email: str, context: dict[str, Any]) -> VerificationResult:
        if not self.api_key:
            raise ValueError("BOUNCER_API_KEY is required when CONTACT_VERIFICATION_PROVIDER=bouncer")
        if not email:
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="unknown",
                reason="No email address found.",
                score=0,
            )
        if not EMAIL_RE.match(email):
            return VerificationResult(
                provider=self.provider_id,
                email=email,
                status="invalid",
                reason="Email syntax is invalid. Bouncer was not called.",
                score=20,
            )

        params: dict[str, Any] = {
            "email": email,
            "timeout": _bouncer_timeout(context.get("timeout"), self.timeout_seconds),
        }
        response = httpx.get(
            self.endpoint,
            headers={"x-api-key": self.api_key},
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Bouncer returned a non-object response")
        return self._normalize_response(email, payload)

    def _normalize_response(self, email: str, payload: dict[str, Any]) -> VerificationResult:
        raw_status = str(payload.get("status") or "unknown").lower().strip()
        raw_reason = str(payload.get("reason") or "unknown").lower().strip()
        status, score = _bouncer_status(raw_status, payload)
        return VerificationResult(
            provider=self.provider_id,
            email=str(payload.get("email") or email),
            status=status,
            reason=_bouncer_reason(raw_status, raw_reason, payload),
            score=score,
            raw=payload,
        )


class EmailVerificationTool:
    name = "email_syntax"
    slot = ToolSlot.VERIFY

    def __init__(
        self,
        *,
        provider: str = "syntax",
        endpoint: str | None = None,
        api_key: str | None = None,
        bouncer_api_key: str | None = None,
        bouncer_api_endpoint: str | None = None,
        zerobounce_api_key: str | None = None,
        zerobounce_api_endpoint: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.api_key = api_key
        self.bouncer_api_key = bouncer_api_key
        self.bouncer_api_endpoint = bouncer_api_endpoint
        self.zerobounce_api_key = zerobounce_api_key
        self.zerobounce_api_endpoint = zerobounce_api_endpoint
        self.timeout_seconds = timeout_seconds
        self.verifier = build_email_verifier(
            provider=provider,
            endpoint=endpoint,
            api_key=api_key,
            bouncer_api_key=bouncer_api_key,
            bouncer_api_endpoint=bouncer_api_endpoint,
            zerobounce_api_key=zerobounce_api_key,
            zerobounce_api_endpoint=zerobounce_api_endpoint,
            timeout_seconds=timeout_seconds,
        )

    def run(self, context: dict[str, Any]) -> ToolResult:
        start = perf_counter()
        email = str(context.get("email") or "").strip()
        result = self.verifier.verify(email, context)
        data = result.as_tool_data()
        latency_ms = round((perf_counter() - start) * 1000)
        return ToolResult(
            provider=result.provider,
            slot=self.slot,
            data=data,
            confidence=int(data["score"]),
            latency_ms=latency_ms,
            raw=data.get("raw") or {"email": email},
        )


def build_email_verifier(
    *,
    provider: str,
    endpoint: str | None,
    api_key: str | None,
    bouncer_api_key: str | None,
    bouncer_api_endpoint: str | None,
    zerobounce_api_key: str | None,
    zerobounce_api_endpoint: str | None,
    timeout_seconds: float,
) -> EmailVerifier:
    normalized = (provider or "syntax").strip().lower()
    if normalized in {"syntax", "local"}:
        return SyntaxEmailVerifier()
    if normalized == "http":
        return HttpEmailVerifier(endpoint=endpoint, api_key=api_key, timeout_seconds=timeout_seconds)
    if normalized == "bouncer":
        return BouncerEmailVerifier(
            api_key=bouncer_api_key or api_key,
            endpoint=bouncer_api_endpoint or endpoint,
            timeout_seconds=timeout_seconds,
        )
    if normalized == "zerobounce":
        return ZeroBounceEmailVerifier(
            api_key=zerobounce_api_key or api_key,
            endpoint=zerobounce_api_endpoint or endpoint,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unknown contact verification provider: {provider}")


def _bouncer_status(raw_status: str, payload: dict[str, Any]) -> tuple[str, int]:
    score = _quality_score(payload.get("score"))
    if raw_status == "deliverable":
        return "valid", score or 95
    if raw_status == "risky":
        return "risky", score or 55
    if raw_status == "undeliverable":
        return "invalid", score if score is not None and score <= 40 else 10
    if raw_status == "unknown":
        return "unknown", score or 30
    return "unknown", score or 30


def _bouncer_reason(raw_status: str, raw_reason: str, payload: dict[str, Any]) -> str:
    parts = [f"Bouncer returned {raw_status or 'unknown'}."]
    if raw_reason:
        parts.append(f"Reason: {raw_reason}.")
    retry_after = str(payload.get("retryAfter") or "").strip()
    if retry_after:
        parts.append(f"Retry after: {retry_after}.")
    toxic = str(payload.get("toxic") or "").strip()
    if toxic and toxic != "unknown":
        parts.append(f"Toxicity: {toxic}.")
    return " ".join(parts)


def _bouncer_timeout(value: Any, fallback_seconds: float) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = int(round(fallback_seconds))
    return max(1, min(30, timeout or 10))


def _zerobounce_status(
    raw_status: str,
    sub_status: str,
    payload: dict[str, Any],
) -> tuple[str, int]:
    quality_score = _quality_score(payload.get("quality_score"))
    if raw_status == "valid":
        return "valid", quality_score or 95
    if raw_status == "catch-all":
        return "risky", quality_score or 55
    if raw_status in {"invalid", "spamtrap", "abuse", "do_not_mail"}:
        return "invalid", quality_score if quality_score is not None and quality_score <= 30 else 10
    if raw_status == "unknown":
        return "unknown", quality_score or 30
    if sub_status in {
        "mail_server_temporary_error",
        "mail_server_did_not_respond",
        "greylisted",
        "antispam_system",
    }:
        return "unknown", quality_score or 30
    return "unknown", quality_score or 30


def _quality_score(value: Any) -> int | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score <= 1:
        score *= 100
    return max(0, min(100, int(round(score))))


def _zerobounce_reason(raw_status: str, sub_status: str, payload: dict[str, Any]) -> str:
    parts = [f"ZeroBounce returned {raw_status or 'unknown'}."]
    if sub_status:
        parts.append(f"Sub-status: {sub_status}.")
    did_you_mean = str(payload.get("did_you_mean") or "").strip()
    if did_you_mean:
        parts.append(f"Suggested correction: {did_you_mean}.")
    return " ".join(parts)


class EmailSyntaxVerifyTool(EmailVerificationTool):
    def __init__(self) -> None:
        super().__init__(provider="syntax")
