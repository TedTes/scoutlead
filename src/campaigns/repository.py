from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from campaigns.schemas import CampaignCreate, CampaignStage, CampaignStatus
from campaigns.state import assert_campaign_transition
from db.models import CampaignModel
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class CampaignRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, campaign: CampaignCreate) -> CampaignModel:
        data = campaign.model_dump(mode="json")
        model = CampaignModel(
            id=new_id("campaign"),
            name=data.pop("name") or f"Campaign {utcnow().date().isoformat()}",
            status=CampaignStatus.DRAFT.value,
            stage=CampaignStage.DISCOVERY.value,
            **data,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[CampaignModel]:
        return list(self.session.scalars(select(CampaignModel).order_by(CampaignModel.created_at.desc())))

    def list_by_product(self, product_id: str) -> list[CampaignModel]:
        statement = (
            select(CampaignModel)
            .where(CampaignModel.product_id == product_id)
            .order_by(CampaignModel.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get(self, campaign_id: str) -> CampaignModel:
        model = self.session.get(CampaignModel, campaign_id)
        if model is None:
            raise NotFoundError("campaign not found", {"campaign_id": campaign_id})
        return model

    def update_status(
        self,
        campaign_id: str,
        status: CampaignStatus,
        *,
        stage: CampaignStage | None = None,
        failure_reason: str | None = None,
    ) -> CampaignModel:
        model = self.get(campaign_id)
        current = CampaignStatus(model.status)
        assert_campaign_transition(current, status)
        model.status = status.value
        if stage is not None:
            model.stage = stage.value
        if failure_reason is not None:
            model.failure_reason = failure_reason
        if status == CampaignStatus.COMPLETED:
            model.completed_at = utcnow()
            model.stage = CampaignStage.COMPLETE.value
        self.session.commit()
        self.session.refresh(model)
        return model
