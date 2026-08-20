from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import DiscoveryCandidateModel
from discovery.schemas import DiscoveryCandidateCreate
from shared.errors import NotFoundError
from shared.utils import new_id, normalize_url


class DiscoveryCandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, candidate: DiscoveryCandidateCreate) -> DiscoveryCandidateModel:
        existing = self.find_existing(candidate.campaign_id, candidate.title, candidate.url)
        if existing:
            existing.query = candidate.query
            existing.snippet = candidate.snippet
            existing.geography = candidate.geography
            existing.contact_email = candidate.contact_email
            existing.source = candidate.source
            existing.raw = candidate.raw
            existing.candidate_type = candidate.candidate_type.value
            existing.confidence = candidate.confidence
            existing.rejection_reason = candidate.rejection_reason
            self.session.commit()
            self.session.refresh(existing)
            return existing

        model = DiscoveryCandidateModel(
            id=new_id("candidate"),
            campaign_id=candidate.campaign_id,
            product_id=candidate.product_id,
            lead_id=None,
            query=candidate.query,
            title=candidate.title,
            url=normalize_url(candidate.url),
            snippet=candidate.snippet,
            geography=candidate.geography,
            contact_email=candidate.contact_email,
            source=candidate.source,
            raw=candidate.raw,
            candidate_type=candidate.candidate_type.value,
            confidence=candidate.confidence,
            rejection_reason=candidate.rejection_reason,
            promoted_at=None,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def get(self, candidate_id: str) -> DiscoveryCandidateModel:
        model = self.session.get(DiscoveryCandidateModel, candidate_id)
        if model is None:
            raise NotFoundError("discovery candidate not found", {"candidate_id": candidate_id})
        return model

    def list_by_campaign(self, campaign_id: str) -> list[DiscoveryCandidateModel]:
        statement = (
            select(DiscoveryCandidateModel)
            .where(DiscoveryCandidateModel.campaign_id == campaign_id)
            .order_by(DiscoveryCandidateModel.created_at)
        )
        return list(self.session.scalars(statement))

    def mark_promoted(self, candidate_id: str, lead_id: str) -> DiscoveryCandidateModel:
        model = self.get(candidate_id)
        model.lead_id = lead_id
        model.promoted_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return model

    def find_existing(
        self, campaign_id: str, title: str, url: str | None = None
    ) -> DiscoveryCandidateModel | None:
        candidates = self.list_by_campaign(campaign_id)
        normalized_title = title.strip().lower()
        normalized_url = normalize_url(url)
        for candidate in candidates:
            if normalized_url and candidate.url == normalized_url:
                return candidate
            if candidate.title.strip().lower() == normalized_title:
                return candidate
        return None
