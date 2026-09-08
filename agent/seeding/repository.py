from __future__ import annotations

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from canonical.repository import CanonicalLeadLink, CanonicalRepository
from db.models import BusinessModel, ContactModel, SourceObservationModel
from seeding.schemas import BusinessSeedInput


class BusinessSeedRepository:
    def __init__(self, session: Session, *, embedding: EmbeddingClient | None = None) -> None:
        self.session = session
        self.canonical = CanonicalRepository(session, embedding=embedding)

    def upsert(self, seed: BusinessSeedInput, *, batch_id: str) -> CanonicalLeadLink:
        return self.canonical.upsert_from_discovery_result(
            company_name=seed.company_name,
            website_url=seed.website_url,
            contact_email=seed.contact_email,
            geography=seed.geography or seed.seed_market,
            description=seed.description,
            source=seed.source,
            raw=seed_raw_payload(seed, batch_id=batch_id),
        )

    def business_ids(self) -> set[str]:
        return set(self.session.scalars(select(BusinessModel.id)))

    def contact_ids(self) -> set[str]:
        return set(self.session.scalars(select(ContactModel.id)))

    def source_observation_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(SourceObservationModel)) or 0)


def seed_raw_payload(seed: BusinessSeedInput, *, batch_id: str) -> dict:
    external_id = seed.external_id or _seed_external_id(seed)
    source_input = {
        "query": seed.query,
        "geography": seed.seed_market or seed.geography,
        "source_type": "seed_import",
        "source_request_prompt": seed.query,
        "source_request_intent": {
            "business_category": "home service painting providers",
            "location": seed.seed_market or seed.geography,
            "required_signals": seed.signals,
            "search_query": seed.query,
        },
    }
    raw = {
        **seed.raw,
        "company_name": seed.company_name,
        "website_url": seed.website_url,
        "contact_email": seed.contact_email,
        "contact_name": seed.contact_name,
        "contact_role": seed.contact_role,
        "contact_phone": seed.phone,
        "phone": seed.phone,
        "geography": seed.geography,
        "formattedAddress": seed.address or seed.geography,
        "address": seed.address,
        "description": seed.description,
        "source": seed.source,
        "source_url": seed.source_url,
        "listingUrl": seed.source_url,
        "external_id": external_id,
        "query": seed.query,
        "search_query": seed.query,
        "signals": seed.signals,
        "operator_type": seed.operator_type,
        "seed_batch_id": batch_id,
        "seed_niche": seed.seed_niche,
        "seed_market": seed.seed_market,
        "seed_source": seed.source,
        "extraction_method": "seed_import",
        "source_input": source_input,
        "source_request_intent": source_input["source_request_intent"],
    }
    return {key: value for key, value in raw.items() if value not in (None, "", [])}


def _seed_external_id(seed: BusinessSeedInput) -> str:
    identity = "|".join(
        [
            normalize_domain(seed.website_url) or "",
            normalize_phone(seed.phone) or "",
            normalize_business_name(seed.company_name),
            (seed.seed_market or seed.geography or "").lower(),
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"seed:{digest}"
