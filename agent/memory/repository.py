from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import CampaignMemoryModel
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
