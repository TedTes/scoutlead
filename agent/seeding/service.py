from __future__ import annotations

from collections.abc import Iterable
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from business_validation.validation import BusinessValidationService
from canonical.repository import CanonicalLeadLink
from canonical.semantics import semantic_key
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SourceObservationModel,
)
from seeding.repository import BusinessSeedRepository
from seeding.schemas import BusinessSeedImportSummary, BusinessSeedInput


class BusinessSeedService:
    def __init__(self, session: Session, *, embedding: EmbeddingClient | None = None) -> None:
        self.session = session
        self.repository = BusinessSeedRepository(session, embedding=embedding)

    def import_seeds(
        self,
        seeds: Iterable[BusinessSeedInput],
        *,
        batch_id: str,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> BusinessSeedImportSummary:
        summary = BusinessSeedImportSummary(batch_id=batch_id, dry_run=dry_run)
        seed_rows = list(seeds)
        if limit is not None:
            seed_rows = seed_rows[:limit]
        _validate_batch_scope(seed_rows, batch_id=batch_id)
        known_business_ids = self.repository.business_ids()
        known_contact_ids = self.repository.contact_ids()
        before_observation_count = self.repository.source_observation_count()

        for seed in seed_rows:
            summary.rows_read += 1
            summary.rows_valid += 1
            if dry_run:
                continue

            link = self.repository.upsert(seed, batch_id=batch_id)
            self._validate_imported_business(link)
            if link.business_id:
                if link.business_id in known_business_ids:
                    summary.businesses_updated += 1
                else:
                    summary.businesses_created += 1
                    known_business_ids.add(link.business_id)
            if link.contact_id and link.contact_id not in known_contact_ids:
                summary.contacts_created += 1
                known_contact_ids.add(link.contact_id)

        if dry_run:
            self.session.rollback()
            return summary

        summary.source_observations_created = max(
            0,
            self.repository.source_observation_count() - before_observation_count,
        )
        self.repository.complete_seed_batch(
            batch_id=batch_id,
            found_count=summary.rows_valid,
            inserted_count=summary.businesses_created,
            updated_count=summary.businesses_updated,
            source_observation_count=summary.source_observations_created,
        )
        self.session.commit()
        return summary

    def _validate_imported_business(self, link: CanonicalLeadLink) -> None:
        if not link.business_id or not link.source_observation_id:
            return
        business = self.session.get(BusinessModel, link.business_id)
        observation = self.session.get(SourceObservationModel, link.source_observation_id)
        membership = self.session.scalar(
            select(BusinessNicheMembershipModel)
            .where(
                BusinessNicheMembershipModel.business_id == link.business_id,
                BusinessNicheMembershipModel.source_observation_id
                == link.source_observation_id,
            )
            .limit(1)
        )
        if business is None or observation is None or membership is None:
            return
        niche = self.session.get(NicheModel, membership.niche_id)
        if niche is None:
            return
        segment = SimpleNamespace(
            niche_id=niche.id,
            market_key=membership.market_key,
            market_label=_seed_market_label(observation, membership.market_key),
            niche=niche,
        )
        validator = BusinessValidationService(self.session)
        candidates = validator.evaluate_observation(
            business=business,
            observation=observation,
            segment=segment,
        )
        validator.record(candidates, commit=False)


def _validate_batch_scope(seeds: list[BusinessSeedInput], *, batch_id: str) -> None:
    niches = {semantic_key(seed.seed_niche) for seed in seeds}
    markets = {semantic_key(seed.seed_market or seed.geography) or "unknown" for seed in seeds}
    if len(niches) > 1:
        raise ValueError(f"seed batch {batch_id} cannot contain more than one niche")
    if len(markets) > 1:
        raise ValueError(f"seed batch {batch_id} cannot contain more than one market")


def _seed_market_label(
    observation: SourceObservationModel,
    fallback: str,
) -> str:
    payload = observation.raw_payload or {}
    return str(
        payload.get("seed_market")
        or payload.get("geography")
        or payload.get("city")
        or fallback
    )
