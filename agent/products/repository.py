from __future__ import annotations

from sqlalchemy import delete, func, or_, select
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
    ProductSourceDraftModel,
    QueueJobModel,
    ToolCallModel,
)
from products.schemas import ProductCreate, ProductUpdate
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow


class ProductRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, product: ProductCreate) -> ProductModel:
        data = product.model_dump(mode="python")
        self._ensure_criterion_ids(data)
        source_fingerprint = data.get("source_fingerprint")
        if source_fingerprint:
            existing = self.find_by_source_fingerprint(source_fingerprint)
            if existing is not None:
                raise ConflictError(
                    "product already exists for this source",
                    {
                        "product_id": existing.id,
                        "product_name": existing.product_name,
                        "source_url": existing.source_url,
                    },
                )
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

    def find_by_source_fingerprint(self, source_fingerprint: str | None) -> ProductModel | None:
        if not source_fingerprint:
            return None
        return self.session.scalar(
            select(ProductModel).where(ProductModel.source_fingerprint == source_fingerprint)
        )

    def find_active_by_product_name(self, product_name: str | None) -> ProductModel | None:
        if not product_name:
            return None
        results = list(
            self.session.scalars(
                select(ProductModel)
                .where(func.lower(ProductModel.product_name) == product_name.lower())
                .where(ProductModel.archived_at.is_(None))
                .order_by(ProductModel.created_at.desc())
                .limit(2)
            )
        )
        return results[0] if len(results) == 1 else None

    def find_source_draft(
        self,
        *,
        source_fingerprint: str | None,
        context_fingerprint: str | None,
    ) -> ProductSourceDraftModel | None:
        if not source_fingerprint or not context_fingerprint:
            return None
        return self.session.scalar(
            select(ProductSourceDraftModel)
            .where(ProductSourceDraftModel.source_fingerprint == source_fingerprint)
            .where(ProductSourceDraftModel.context_fingerprint == context_fingerprint)
        )

    def find_latest_source_draft(
        self,
        *,
        source_fingerprint: str | None,
    ) -> ProductSourceDraftModel | None:
        if not source_fingerprint:
            return None
        return self.session.scalar(
            select(ProductSourceDraftModel)
            .where(ProductSourceDraftModel.source_fingerprint == source_fingerprint)
            .order_by(ProductSourceDraftModel.updated_at.desc())
            .limit(1)
        )

    def upsert_source_draft(
        self,
        *,
        source: str,
        source_url: str | None,
        source_fingerprint: str,
        context: str | None,
        context_fingerprint: str,
        target_geography: str,
        inference: dict,
    ) -> ProductSourceDraftModel:
        model = self.find_source_draft(
            source_fingerprint=source_fingerprint,
            context_fingerprint=context_fingerprint,
        )
        if model is None:
            model = ProductSourceDraftModel(
                id=new_id("product_draft"),
                source=source,
                source_url=source_url,
                source_fingerprint=source_fingerprint,
                context=context,
                context_fingerprint=context_fingerprint,
                target_geography=target_geography,
                inference=inference,
            )
            self.session.add(model)
        else:
            model.source = source
            model.source_url = source_url
            model.context = context
            model.target_geography = target_geography
            model.inference = inference
            model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def attach_source_metadata(
        self,
        product_id: str,
        *,
        source_url: str,
        source_fingerprint: str,
    ) -> ProductModel:
        existing = self.find_by_source_fingerprint(source_fingerprint)
        if existing is not None and existing.id != product_id:
            raise ConflictError(
                "source is already attached to another product",
                {
                    "product_id": existing.id,
                    "product_name": existing.product_name,
                    "source_url": existing.source_url,
                },
            )
        model = self.get(product_id)
        model.source_url = source_url
        model.source_fingerprint = source_fingerprint
        model.source_last_checked_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def update(self, product_id: str, update: ProductUpdate) -> ProductModel:
        model = self.get(product_id)
        data = update.model_dump(mode="python", exclude_unset=True)
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
