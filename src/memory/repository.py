from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignMemoryModel, LearningSummaryModel
from memory.schemas import CampaignMemoryCreate
from shared.utils import new_id, utcnow


class MemoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_observation(self, observation: CampaignMemoryCreate) -> CampaignMemoryModel:
        model = CampaignMemoryModel(
            id=new_id("memory"),
            created_at=utcnow(),
            **observation.model_dump(mode="json"),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list_observations(self, product_id: str | None = None) -> list[CampaignMemoryModel]:
        statement = select(CampaignMemoryModel).order_by(CampaignMemoryModel.created_at.desc())
        if product_id is not None:
            statement = statement.where(CampaignMemoryModel.product_id == product_id)
        return list(self.session.scalars(statement))

    def list_summaries(self, product_id: str | None = None) -> list[LearningSummaryModel]:
        statement = select(LearningSummaryModel).order_by(LearningSummaryModel.updated_at.desc())
        if product_id is not None:
            statement = statement.where(LearningSummaryModel.product_id == product_id)
        return list(self.session.scalars(statement))

    def upsert_summary(
        self, product_id: str, summary: str, evidence: list[str], campaign_id: str | None = None
    ) -> LearningSummaryModel:
        statement = select(LearningSummaryModel).where(
            LearningSummaryModel.product_id == product_id,
            LearningSummaryModel.campaign_id == campaign_id,
        )
        existing = self.session.scalar(statement)
        if existing:
            existing.summary = summary
            existing.evidence = evidence
            existing.updated_at = utcnow()
            self.session.commit()
            self.session.refresh(existing)
            return existing

        model = LearningSummaryModel(
            id=new_id("learning"),
            product_id=product_id,
            campaign_id=campaign_id,
            summary=summary,
            evidence=evidence,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model
