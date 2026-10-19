from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from business_validation.repository import ValidationRepository
from shared.utils import utcnow


REQUIRED_VALIDATIONS = frozenset(
    {"identity", "business_identity", "trade", "location"}
)


@dataclass(frozen=True)
class PublicationDecision:
    status: str
    reasons: tuple[str, ...]
    missing: tuple[str, ...] = ()

    @property
    def publishable(self) -> bool:
        return self.status == "publishable"


def publication_decision(results: Iterable[object]) -> PublicationDecision:
    latest: dict[str, object] = {}
    for result in results:
        validation_type = str(getattr(result, "validation_type", ""))
        if validation_type in REQUIRED_VALIDATIONS:
            latest.setdefault(validation_type, result)

    missing = tuple(sorted(REQUIRED_VALIDATIONS - set(latest)))
    failed = [
        result for result in latest.values() if getattr(result, "status", None) == "failed"
    ]
    if failed:
        return PublicationDecision(
            status="rejected",
            reasons=tuple(str(getattr(result, "reason", "Validation failed.")) for result in failed),
            missing=missing,
        )

    uncertain = [
        result
        for result in latest.values()
        if getattr(result, "status", None) != "passed"
        or int(getattr(result, "confidence", 0)) < 80
    ]
    if missing or uncertain:
        return PublicationDecision(
            status="needs_review",
            reasons=tuple(
                str(getattr(result, "reason", "Validation is uncertain."))
                for result in uncertain
            ),
            missing=missing,
        )

    return PublicationDecision(
        status="publishable",
        reasons=("All required business validations passed.",),
    )


def business_is_publishable(
    session: Session,
    *,
    business_id: str,
    niche_id: str,
    market_key: str,
    allow_unvalidated: bool = True,
) -> bool:
    current = ValidationRepository(session).latest_current(
        business_id,
        niche_id=niche_id,
        market_key=market_key,
        now=utcnow(),
    )
    if not current:
        return allow_unvalidated
    return publication_decision(current.values()).publishable
