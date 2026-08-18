from __future__ import annotations

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from db.models import (
    AgentRunModel,
    AgentStepModel,
    CampaignMemoryModel,
    CampaignModel,
    ConversationEventModel,
    ConversationModel,
    LeadModel,
    LearningSummaryModel,
    MessageModel,
    ProductModel,
    QueueJobModel,
    ToolCallModel,
)
from products.schemas import ProductCreate, ProductUpdate
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, product: ProductCreate) -> ProductModel:
        data = product.model_dump(mode="json")
        self._ensure_criterion_ids(data)
        model = ProductModel(id=new_id("product"), **data)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[ProductModel]:
        return list(self.session.scalars(select(ProductModel).order_by(ProductModel.created_at.desc())))

    def get(self, product_id: str) -> ProductModel:
        model = self.session.get(ProductModel, product_id)
        if model is None:
            raise NotFoundError("product not found", {"product_id": product_id})
        return model

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        model = self.get(product_id)
        data = update.model_dump(mode="json", exclude_unset=True)
        if "qualification_criteria" in data:
            self._ensure_criterion_ids(data)
        for field, value in data.items():
            setattr(model, field, value)
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def archive(self, product_id: str) -> ProductModel:
        model = self.get(product_id)
        model.archived_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def delete(self, product_id: str) -> None:
        model = self.get(product_id)
        campaign_ids = list(
            self.session.scalars(select(CampaignModel.id).where(CampaignModel.product_id == product_id))
        )
        conversation_ids = list(
            self.session.scalars(
                select(ConversationModel.id).where(ConversationModel.product_id == product_id)
            )
        )
        message_ids = list(
            self.session.scalars(select(MessageModel.id).where(MessageModel.product_id == product_id))
        )

        if conversation_ids or message_ids:
            event_conditions = []
            if conversation_ids:
                event_conditions.append(ConversationEventModel.conversation_id.in_(conversation_ids))
            if message_ids:
                event_conditions.append(ConversationEventModel.message_id.in_(message_ids))
            self.session.execute(delete(ConversationEventModel).where(or_(*event_conditions)))

        if campaign_ids:
            self.session.execute(delete(ToolCallModel).where(ToolCallModel.campaign_id.in_(campaign_ids)))
            self.session.execute(delete(AgentStepModel).where(AgentStepModel.campaign_id.in_(campaign_ids)))
            self.session.execute(delete(AgentRunModel).where(AgentRunModel.campaign_id.in_(campaign_ids)))
            self.session.execute(
                delete(QueueJobModel).where(QueueJobModel.payload["campaign_id"].as_string().in_(campaign_ids))
            )

        self.session.execute(delete(ConversationModel).where(ConversationModel.product_id == product_id))
        self.session.execute(delete(MessageModel).where(MessageModel.product_id == product_id))
        self.session.execute(delete(LeadModel).where(LeadModel.product_id == product_id))
        self.session.execute(delete(CampaignMemoryModel).where(CampaignMemoryModel.product_id == product_id))
        self.session.execute(delete(LearningSummaryModel).where(LearningSummaryModel.product_id == product_id))
        self.session.execute(delete(CampaignModel).where(CampaignModel.product_id == product_id))
        self.session.execute(
            delete(QueueJobModel).where(QueueJobModel.payload["product_id"].as_string() == product_id)
        )
        self.session.delete(model)
        self.session.commit()

    @staticmethod
    def _ensure_criterion_ids(data: dict) -> None:
        for criterion in data.get("qualification_criteria", []):
            if not criterion.get("id"):
                criterion["id"] = new_id("criterion")
