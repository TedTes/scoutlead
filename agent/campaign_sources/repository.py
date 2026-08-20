from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from campaign_sources.schemas import CampaignSourceCreate, CampaignSourceSlot
from db.models import CampaignSourceModel
from shared.errors import NotFoundError
from shared.utils import new_id


class CampaignSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_many(self, sources: list[CampaignSourceCreate]) -> list[CampaignSourceModel]:
        models = [
            CampaignSourceModel(
                id=new_id("campaign_source"),
                **source.model_dump(mode="json"),
            )
            for source in sources
        ]
        self.session.add_all(models)
        self.session.commit()
        for model in models:
            self.session.refresh(model)
        return models

    def list_by_campaign(
        self,
        campaign_id: str,
        *,
        slot: CampaignSourceSlot | str | None = None,
        enabled_only: bool = False,
    ) -> list[CampaignSourceModel]:
        statement = select(CampaignSourceModel).where(CampaignSourceModel.campaign_id == campaign_id)
        if slot is not None:
            slot_value = slot.value if isinstance(slot, CampaignSourceSlot) else slot
            statement = statement.where(CampaignSourceModel.slot == slot_value)
        if enabled_only:
            statement = statement.where(CampaignSourceModel.enabled.is_(True))
        statement = statement.order_by(CampaignSourceModel.priority.asc(), CampaignSourceModel.created_at.asc())
        return list(self.session.scalars(statement))

    def get(self, source_id: str) -> CampaignSourceModel:
        model = self.session.get(CampaignSourceModel, source_id)
        if model is None:
            raise NotFoundError("campaign source not found", {"source_id": source_id})
        return model

    def replace_for_campaign(self, campaign_id: str, sources: list[CampaignSourceCreate]) -> list[CampaignSourceModel]:
        self.session.execute(delete(CampaignSourceModel).where(CampaignSourceModel.campaign_id == campaign_id))
        self.session.commit()
        return self.create_many(sources)
