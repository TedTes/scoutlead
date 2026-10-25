from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Collection

from canonical.normalization import stable_content_hash
from shared.utils import utcnow


@dataclass(frozen=True)
class ObservationIntegrityCheck:
    name: str
    status: str
    detail: str

    def as_evidence(self) -> dict[str, Any]:
        return {
            "check": self.name,
            "passed": self.status == "passed",
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ObservationIntegrityResult:
    status: str
    confidence: int
    checks: tuple[ObservationIntegrityCheck, ...]

    @property
    def failures(self) -> tuple[str, ...]:
        return tuple(check.detail for check in self.checks if check.status == "failed")

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(check.detail for check in self.checks if check.status == "uncertain")

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return [check.as_evidence() for check in self.checks]


def evaluate_observation_integrity(
    observation: object | None,
    *,
    expected_business_id: str | None = None,
    expected_sources: Collection[str] | None = None,
    now: datetime | None = None,
    stale_after: timedelta | None = None,
    require_locator: bool = False,
) -> ObservationIntegrityResult:
    """Evaluate whether a stored observation is trustworthy evidence.

    This is intentionally a pure, read-only check. It does not decide whether the
    represented business fact is true; downstream extraction and reconciliation do
    that. It verifies that the evidence record is internally intact and attributable.
    """

    if observation is None:
        check = ObservationIntegrityCheck(
            "observation_present",
            "failed",
            "The source observation is missing.",
        )
        return ObservationIntegrityResult("failed", 0, (check,))

    checks: list[ObservationIntegrityCheck] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append(ObservationIntegrityCheck(name, status, detail))

    business_id = str(getattr(observation, "business_id", "") or "")
    business_matches = not expected_business_id or business_id == expected_business_id
    add(
        "business_association",
        "passed" if business_matches else "failed",
        (
            "Observation belongs to the expected business."
            if business_matches
            else "Observation is attached to a different business than its claim."
        ),
    )

    source = str(getattr(observation, "source", "") or "").strip()
    source_valid = bool(source) and (
        expected_sources is None or source in expected_sources
    )
    add(
        "source_provenance",
        "passed" if source_valid else "failed",
        (
            f"Observation source {source!r} is attributable."
            if source_valid
            else (
                f"Observation source {source!r} is not allowed for this collector."
                if source
                else "Observation has no source identifier."
            )
        ),
    )

    payload = getattr(observation, "raw_payload", None)
    payload_valid = isinstance(payload, dict) and bool(payload)
    add(
        "payload_present",
        "passed" if payload_valid else "failed",
        "Observation has a non-empty JSON payload."
        if payload_valid
        else "Observation payload is empty or is not a JSON object.",
    )

    stored_hash = str(getattr(observation, "content_hash", "") or "")
    expected_hash = stable_content_hash(payload) if payload_valid else None
    hash_valid = bool(expected_hash) and stored_hash == expected_hash
    add(
        "content_hash",
        "passed" if hash_valid else "failed",
        "Stored content hash matches the observation payload."
        if hash_valid
        else "Stored content hash does not match the observation payload.",
    )

    observed_at = getattr(observation, "observed_at", None)
    current_time = _aware(now or utcnow())
    timestamp_status = "passed"
    timestamp_detail = "Observation timestamp is plausible."
    if not isinstance(observed_at, datetime):
        timestamp_status = "failed"
        timestamp_detail = "Observation has no valid observation timestamp."
    else:
        observed_at = _aware(observed_at)
        if observed_at > current_time + timedelta(minutes=5):
            timestamp_status = "uncertain"
            timestamp_detail = "Observation timestamp is unexpectedly in the future."
        elif stale_after is not None and observed_at < current_time - stale_after:
            timestamp_status = "uncertain"
            timestamp_detail = "Observation is older than the configured freshness window."
    add("observed_at", timestamp_status, timestamp_detail)

    locators = (
        getattr(observation, "external_id", None),
        getattr(observation, "source_url", None),
        getattr(observation, "query_signature", None),
    )
    has_locator = any(str(value or "").strip() for value in locators)
    add(
        "source_locator",
        "passed" if has_locator else ("uncertain" if require_locator else "passed"),
        "Observation has a source locator."
        if has_locator
        else (
            "Observation has no external ID, source URL, or query signature."
            if require_locator
            else "A source locator is not required for this internal observation."
        ),
    )

    if any(check.status == "failed" for check in checks):
        return ObservationIntegrityResult("failed", 0, tuple(checks))
    if any(check.status == "uncertain" for check in checks):
        return ObservationIntegrityResult("uncertain", 70, tuple(checks))
    return ObservationIntegrityResult("passed", 100, tuple(checks))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
