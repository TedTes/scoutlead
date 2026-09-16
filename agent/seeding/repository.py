from __future__ import annotations

import hashlib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from canonical.normalization import normalize_business_name, normalize_domain, normalize_phone
from canonical.repository import CanonicalLeadLink, CanonicalRepository
from canonical.semantics import semantic_key
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
    SeedBatchModel,
    SourceObservationModel,
)
from seeding.schemas import BusinessSeedInput
from shared.utils import normalize_text, new_id, utcnow


class BusinessSeedRepository:
    def __init__(self, session: Session, *, embedding: EmbeddingClient | None = None) -> None:
        self.session = session
        self.canonical = CanonicalRepository(session, embedding=embedding)

    def upsert(self, seed: BusinessSeedInput, *, batch_id: str) -> CanonicalLeadLink:
        link = self.canonical.upsert_from_discovery_result(
            company_name=seed.company_name,
            website_url=seed.website_url,
            contact_email=seed.contact_email,
            geography=seed.geography or seed.seed_market,
            description=seed.description,
            source=seed.source,
            raw=seed_raw_payload(seed, batch_id=batch_id),
        )
        if link.business_id:
            self._record_seed_membership(seed, batch_id=batch_id, link=link)
        return link

    def business_ids(self) -> set[str]:
        return set(self.session.scalars(select(BusinessModel.id)))

    def contact_ids(self) -> set[str]:
        return set(self.session.scalars(select(ContactModel.id)))

    def source_observation_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(SourceObservationModel)) or 0)

    def niche_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(NicheModel)) or 0)

    def seed_batch_count(self) -> int:
        return int(self.session.scalar(select(func.count()).select_from(SeedBatchModel)) or 0)

    def membership_count(self) -> int:
        return int(
            self.session.scalar(select(func.count()).select_from(BusinessNicheMembershipModel)) or 0
        )

    def complete_seed_batch(
        self,
        *,
        batch_id: str,
        found_count: int,
        inserted_count: int,
        updated_count: int,
        source_observation_count: int,
    ) -> None:
        seed_batch = self.session.get(SeedBatchModel, batch_id)
        if seed_batch is None:
            return
        seed_batch.status = "completed"
        seed_batch.completed_at = utcnow()
        seed_batch.found_count = found_count
        seed_batch.inserted_count = inserted_count
        seed_batch.updated_count = updated_count
        seed_batch.source_observation_count = source_observation_count
        self.session.flush()

    def _record_seed_membership(
        self,
        seed: BusinessSeedInput,
        *,
        batch_id: str,
        link: CanonicalLeadLink,
    ) -> None:
        niche = self._upsert_niche(seed)
        seed_batch = self._upsert_seed_batch(seed, batch_id=batch_id, niche_id=niche.id)
        self._upsert_business_niche_membership(
            seed,
            business_id=link.business_id,
            niche_id=niche.id,
            seed_batch_id=seed_batch.id,
            source_observation_id=link.source_observation_id,
        )

    def _upsert_niche(self, seed: BusinessSeedInput) -> NicheModel:
        slug = _niche_slug(seed.seed_niche)
        niche = self.session.scalar(select(NicheModel).where(NicheModel.slug == slug).limit(1))
        if niche is None:
            niche = NicheModel(
                id=new_id("niche"),
                slug=slug,
                label=_niche_label(seed.seed_niche),
                category=normalize_text(seed.seed_niche),
                default_query=seed.query,
                active=True,
            )
            self.session.add(niche)
            self.session.flush()
            return niche
        niche.label = niche.label or _niche_label(seed.seed_niche)
        niche.category = niche.category or normalize_text(seed.seed_niche)
        niche.default_query = niche.default_query or seed.query
        niche.active = True
        self.session.flush()
        return niche

    def _upsert_seed_batch(
        self,
        seed: BusinessSeedInput,
        *,
        batch_id: str,
        niche_id: str,
    ) -> SeedBatchModel:
        now = utcnow()
        seed_batch = self.session.get(SeedBatchModel, batch_id)
        if seed_batch is None:
            seed_batch = SeedBatchModel(
                id=batch_id,
                niche_id=niche_id,
                market_key=_seed_market_key(seed),
                source=seed.source,
                query=seed.query,
                status="running",
                started_at=now,
                found_count=0,
                inserted_count=0,
                updated_count=0,
                source_observation_count=0,
            )
            self.session.add(seed_batch)
            self.session.flush()
            return seed_batch
        seed_batch.niche_id = seed_batch.niche_id or niche_id
        seed_batch.market_key = seed_batch.market_key or _seed_market_key(seed)
        seed_batch.source = seed_batch.source or seed.source
        seed_batch.query = seed_batch.query or seed.query
        if seed_batch.status != "completed":
            seed_batch.status = "running"
        self.session.flush()
        return seed_batch

    def _upsert_business_niche_membership(
        self,
        seed: BusinessSeedInput,
        *,
        business_id: str,
        niche_id: str,
        seed_batch_id: str,
        source_observation_id: str | None,
    ) -> BusinessNicheMembershipModel:
        now = utcnow()
        market_key = _seed_market_key(seed)
        membership = self.session.scalar(
            select(BusinessNicheMembershipModel)
            .where(
                BusinessNicheMembershipModel.business_id == business_id,
                BusinessNicheMembershipModel.niche_id == niche_id,
                BusinessNicheMembershipModel.market_key == market_key,
            )
            .limit(1)
        )
        evidence = _membership_evidence(
            seed,
            batch_id=seed_batch_id,
            source_observation_id=source_observation_id,
        )
        if membership is None:
            membership = BusinessNicheMembershipModel(
                id=new_id("bizniche"),
                business_id=business_id,
                niche_id=niche_id,
                market_key=market_key,
                confidence=1.0,
                evidence=[evidence],
                source_observation_id=source_observation_id,
                seed_batch_id=seed_batch_id,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(membership)
            self.session.flush()
            return membership

        membership.confidence = max(membership.confidence, 1.0)
        membership.evidence = _append_unique_evidence(membership.evidence or [], evidence)
        membership.source_observation_id = source_observation_id or membership.source_observation_id
        membership.seed_batch_id = seed_batch_id or membership.seed_batch_id
        membership.last_seen_at = now
        self.session.flush()
        return membership


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


def _niche_slug(value: str | None) -> str:
    normalized = normalize_text(value or "uncategorized").lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized or "uncategorized"


def _niche_label(value: str | None) -> str:
    slug = _niche_slug(value)
    return " ".join(part.capitalize() for part in slug.split("_") if part) or "Uncategorized"


def _seed_market_key(seed: BusinessSeedInput) -> str:
    return semantic_key(seed.seed_market or seed.geography) or "unknown"


def _membership_evidence(
    seed: BusinessSeedInput,
    *,
    batch_id: str,
    source_observation_id: str | None,
) -> dict:
    return {
        "type": "seed_import",
        "source": seed.source,
        "batch_id": batch_id,
        "query": seed.query,
        "signals": seed.signals,
        "source_observation_id": source_observation_id,
    }


def _append_unique_evidence(existing: list[dict], evidence: dict) -> list[dict]:
    evidence_key = (
        evidence.get("type"),
        evidence.get("source"),
        evidence.get("batch_id"),
        evidence.get("source_observation_id"),
    )
    for item in existing:
        item_key = (
            item.get("type"),
            item.get("source"),
            item.get("batch_id"),
            item.get("source_observation_id"),
        )
        if item_key == evidence_key:
            return existing
    return [*existing, evidence]
