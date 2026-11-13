from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_attributes.repository import BusinessAttributeRepository, BusinessAttributeValue, attribute_value
from business_attributes.operational import assess_business_operational
from canonical.normalization import external_id_from_raw, first_raw_text, nested_raw
from canonical.website_evidence import assess_website_ownership
from db.models import (
    BusinessModel,
    BusinessAttributeDefinitionModel,
    ContactModel,
    BusinessAttributeModel,
)


VALID_CONTACT_STATUSES = frozenset({"valid", "verified", "passed"})


def sync_observed_business_attributes(
    session: Session,
    *,
    business: BusinessModel,
    observation: BusinessAttributeModel,
    track_changes: bool = True,
) -> int:
    """Materialize observed canonical attributes as scored business facts.

    Only non-null values are written. Missing data therefore remains unknown
    and can never become a false opportunity merely because a source omitted it.
    """

    raw = nested_raw(observation.raw_payload or {})
    values: dict[str, Any] = {
        "business_name": business.display_name,
        "trade_category": business.category_key,
        "provider_business_id": external_id_from_raw(raw),
        "address": business.address,
        "city": first_raw_text(raw, ("city", "locality", "town")) or business.market_key,
        "region": first_raw_text(
            raw,
            ("region", "province", "state", "administrative_area_level_1"),
        ),
        "postal_code": first_raw_text(raw, ("postal_code", "postcode", "zip", "zip_code")),
        "latitude": business.latitude,
        "longitude": business.longitude,
        "phone": business.phone,
        "website_url": business.website_url,
        "domain": business.domain,
        "is_directory": business.is_directory,
        "is_chain": business.is_chain,
        "is_franchise": business.is_franchise,
    }

    operational = assess_business_operational(
        session,
        business=business,
        observation=observation,
    )
    if operational is not None:
        values["business_operational"] = operational.value

    # Presence is only asserted when a Google provider observation exists. The
    # absence of such an observation is unknown, not false.
    if observation.source in {"google_places", "google_places_seed"}:
        values["google_business_profile_present"] = True

    ownership = assess_website_ownership(
        source=observation.source or "",
        payload=observation.raw_payload or {},
        business_name=business.display_name,
        business_phone=business.phone,
    )
    if ownership is not None:
        values["website_ownership"] = ownership.status

    contacts = list(
        session.scalars(
            select(ContactModel)
            .where(ContactModel.business_id == business.id)
            .order_by(ContactModel.last_seen_at.desc())
        )
    )
    verified_email = next(
        (
            contact.email
            for contact in contacts
            if contact.email and contact.verification_status in VALID_CONTACT_STATUSES
        ),
        None,
    )
    values["verified_email"] = verified_email

    contact_form = session.scalar(
        select(BusinessAttributeModel).where(
            BusinessAttributeModel.business_id == business.id,
            BusinessAttributeModel.attribute_key == "contact_form_url",
        )
    )
    contact_form_url = attribute_value(contact_form)
    preferred_channel = (
        "email"
        if verified_email
        else "contact_form"
        if contact_form_url
        else None
    )
    values["preferred_contact_channel"] = preferred_channel

    repository = BusinessAttributeRepository(session)
    defined_keys = set(
        session.scalars(
            select(BusinessAttributeDefinitionModel.key).where(
                BusinessAttributeDefinitionModel.key.in_(values.keys()),
                BusinessAttributeDefinitionModel.status.in_(("active", "derived")),
            )
        )
    )
    written = 0
    confidence = _source_confidence(observation.source)
    for key, value in values.items():
        if key not in defined_keys or value is None or value == "":
            continue
        fact_confidence = operational.confidence if key == "business_operational" and operational else confidence
        source_evidence_id = (
            operational.source_evidence_id
            if key == "business_operational" and operational
            else observation.id
        )
        model = repository.upsert(
            business.id,
            BusinessAttributeValue(
                key=key,
                value=value,
                observed_at=observation.observed_at,
                source_evidence_id=source_evidence_id,
                confidence=fact_confidence,
            ),
            track_change=track_changes,
        )
        written += 1
    return written


def _source_confidence(source: str) -> int:
    if source in {"google_places", "google_places_seed", "openstreetmap"}:
        return 95
    if source in {"company_website_signal", "website_presence_check"}:
        return 90
    return 85
