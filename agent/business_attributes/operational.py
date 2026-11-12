from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from canonical.business_entity import assess_provider_business_entity
from canonical.normalization import first_raw_text, nested_raw
from canonical.website_evidence import assess_website_ownership
from db.models import BusinessModel, ContactModel, BusinessAttributeModel
from shared.utils import utcnow


VALID_CONTACT_STATUSES = frozenset({"valid", "verified", "passed"})
LISTING_SOURCES = frozenset(
    {
        "openstreetmap",
        "openstreetmap_seed",
        "apify",
        "homestars",
        "yellowpages",
    }
)


@dataclass(frozen=True)
class OperationalAssessment:
    value: bool
    confidence: int
    reason: str
    source_evidence_id: str


def assess_business_operational(
    session: Session,
    *,
    business: BusinessModel,
    observation: BusinessAttributeModel,
) -> OperationalAssessment | None:
    """Resolve current operation without requiring a Google Business Profile.

    Explicit provider status wins. Temporary closure and missing status remain
    unknown. Without an explicit status, two independent support families are
    required so a single stale directory or reachable domain cannot qualify a
    business by itself.
    """

    entity = assess_provider_business_entity(
        source=observation.source,
        payload={**(observation.raw_payload or {}), "id": observation.external_id},
    )
    if (
        observation.source
        in {"google_places", "google_places_seed", "openstreetmap", "openstreetmap_seed"}
        and entity.is_business is not True
    ):
        return None
    explicit = _explicit_status(observation.raw_payload or {})
    if explicit == "operational":
        return OperationalAssessment(
            True,
            100 if observation.source in {"google_places", "google_places_seed"} else 95,
            f"{observation.source} explicitly reports the business as operational.",
            observation.id,
        )
    if explicit == "permanently_closed":
        return OperationalAssessment(
            False,
            100,
            f"{observation.source} explicitly reports the business as permanently closed.",
            observation.id,
        )
    if explicit == "temporarily_closed":
        return None

    cutoff = utcnow() - timedelta(days=90)
    observations = list(
        session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id == business.id,
                BusinessAttributeModel.row_type == "evidence",
                BusinessAttributeModel.observed_at >= cutoff,
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        )
    )
    families: set[str] = set()
    supporting_observation = observation

    ownership = next(
        (
            assess_website_ownership(
                source=candidate.source or "",
                payload=candidate.raw_payload or {},
                business_name=business.display_name,
                business_phone=business.phone,
            )
            for candidate in observations
            if candidate.source == "company_website_signal"
        ),
        None,
    )
    if ownership is not None and ownership.status == "passed" and business.website_url and any(
        candidate.source == "company_website_signal"
        and _website_is_reachable(candidate.raw_payload or {})
        for candidate in observations
    ):
        families.add("verified_owned_website")

    verified_contact = session.scalar(
        select(ContactModel.id)
        .where(
            ContactModel.business_id == business.id,
            ContactModel.verification_status.in_(VALID_CONTACT_STATUSES),
        )
        .limit(1)
    )
    if verified_contact is not None:
        families.add("verified_contact")

    listing = next(
        (
            candidate
            for candidate in observations
            if candidate.source in LISTING_SOURCES and candidate.external_id
        ),
        None,
    )
    if listing is not None:
        families.add("current_provider_listing")
        supporting_observation = listing

    if len(families) < 2:
        return None
    return OperationalAssessment(
        True,
        85,
        "Two independent sources support current operation: "
        + ", ".join(sorted(families))
        + ".",
        supporting_observation.id,
    )


def _explicit_status(payload: dict) -> str | None:
    raw = nested_raw(payload)
    value = first_raw_text(raw, ("businessStatus", "business_status"))
    normalized = str(value or "").strip().upper()
    if normalized == "OPERATIONAL":
        return "operational"
    if normalized in {"CLOSED_PERMANENTLY", "PERMANENTLY_CLOSED"}:
        return "permanently_closed"
    if normalized in {"CLOSED_TEMPORARILY", "TEMPORARILY_CLOSED"}:
        return "temporarily_closed"
    return None


def _website_is_reachable(payload: dict) -> bool:
    raw = nested_raw(payload)
    status = first_raw_text(
        raw,
        ("availability_status", "website_status", "status"),
    )
    normalized = str(status or "").strip().lower()
    if normalized in {"present", "available", "active", "reachable"}:
        return True
    http_status = first_raw_text(raw, ("http_status", "status_code"))
    try:
        code = int(float(http_status)) if http_status is not None else None
    except (TypeError, ValueError):
        return False
    return code is not None and 200 <= code < 400
