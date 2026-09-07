from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from campaigns.schemas import CampaignCreate, CampaignStage, CampaignStatus, CampaignUpdate
from campaigns.state import assert_campaign_transition
from db.models import (
    AgentRunModel,
    AgentStepModel,
    CampaignInsightModel,
    CampaignMemoryModel,
    CampaignModel,
    CampaignSourceModel,
    ConversationEventModel,
    ConversationModel,
    DiscoveryCandidateModel,
    LeadModel,
    LearningSummaryModel,
    MessageModel,
    ProductModel,
    QueueJobModel,
    ToolCallModel,
)
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class CampaignRepository:
    def __init__(self, session: Session, *, workspace_id: str | None = None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def create(self, campaign: CampaignCreate) -> CampaignModel:
        data = campaign.model_dump(mode="json")
        data.pop("source_input", None)
        data.pop("source_inputs", None)
        self._assert_product_in_scope(data["product_id"])
        requested_name = data.pop("name") or f"Campaign {utcnow().date().isoformat()}"
        model = CampaignModel(
            id=new_id("campaign"),
            name=self._unique_name(data["product_id"], requested_name),
            status=CampaignStatus.DRAFT.value,
            stage=CampaignStage.DISCOVERY.value,
            **data,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def list(self) -> list[CampaignModel]:
        statement = self._scope(select(CampaignModel).order_by(CampaignModel.created_at.desc()))
        return list(self.session.scalars(statement))

    def list_by_product(self, product_id: str) -> list[CampaignModel]:
        statement = (
            select(CampaignModel)
            .where(CampaignModel.product_id == product_id)
            .order_by(CampaignModel.created_at.desc())
        )
        statement = self._scope(statement)
        return list(self.session.scalars(statement))

    def get(self, campaign_id: str) -> CampaignModel:
        model = self.session.scalar(self._scope(select(CampaignModel).where(CampaignModel.id == campaign_id)))
        if model is None:
            raise NotFoundError("campaign not found", {"campaign_id": campaign_id})
        return model

    def delete(self, campaign_id: str) -> None:
        model = self.get(campaign_id)
        conversation_ids = self.session.scalars(
            select(ConversationModel.id).where(ConversationModel.campaign_id == campaign_id)
        ).all()
        if conversation_ids:
            self.session.execute(
                delete(ConversationEventModel).where(
                    ConversationEventModel.conversation_id.in_(conversation_ids)
                )
            )
        self.session.execute(delete(ToolCallModel).where(ToolCallModel.campaign_id == campaign_id))
        self.session.execute(delete(AgentStepModel).where(AgentStepModel.campaign_id == campaign_id))
        self.session.execute(delete(AgentRunModel).where(AgentRunModel.campaign_id == campaign_id))
        self.session.execute(delete(CampaignSourceModel).where(CampaignSourceModel.campaign_id == campaign_id))
        self.session.execute(delete(ConversationModel).where(ConversationModel.campaign_id == campaign_id))
        self.session.execute(delete(MessageModel).where(MessageModel.campaign_id == campaign_id))
        self.session.execute(delete(DiscoveryCandidateModel).where(DiscoveryCandidateModel.campaign_id == campaign_id))
        self.session.execute(delete(LeadModel).where(LeadModel.campaign_id == campaign_id))
        self.session.execute(delete(CampaignMemoryModel).where(CampaignMemoryModel.campaign_id == campaign_id))
        self.session.execute(delete(CampaignInsightModel).where(CampaignInsightModel.campaign_id == campaign_id))
        self.session.execute(delete(LearningSummaryModel).where(LearningSummaryModel.campaign_id == campaign_id))
        self.session.execute(
            delete(QueueJobModel).where(QueueJobModel.payload["campaign_id"].as_string() == campaign_id)
        )
        self.session.delete(model)
        self.session.commit()

    def update(self, campaign_id: str, update: CampaignUpdate) -> CampaignModel:
        model = self.get(campaign_id)
        data = update.model_dump(mode="python", exclude_unset=True)
        if "name" in data and data["name"] is not None:
            data["name"] = self._unique_name(model.product_id, data["name"], exclude_id=campaign_id)
        for field, value in data.items():
            setattr(model, field, value)
        model.updated_at = utcnow()
        self.session.commit()
        self.session.refresh(model)
        return model

    def _scope(self, statement):
        if not self.workspace_id:
            return statement
        return statement.join(ProductModel, CampaignModel.product_id == ProductModel.id).where(
            ProductModel.workspace_id == self.workspace_id
        )

    def _assert_product_in_scope(self, product_id: str) -> None:
        if not self.workspace_id:
            return
        exists = self.session.scalar(
            select(ProductModel.id)
            .where(ProductModel.id == product_id)
            .where(ProductModel.workspace_id == self.workspace_id)
        )
        if not exists:
            raise NotFoundError("product not found", {"product_id": product_id})

    def _unique_name(self, product_id: str, requested_name: str, *, exclude_id: str | None = None) -> str:
        base_name = _fit_campaign_name(_collapse_spaces(requested_name) or "Untitled list")
        statement = select(CampaignModel.name).where(CampaignModel.product_id == product_id)
        if exclude_id:
            statement = statement.where(CampaignModel.id != exclude_id)
        existing = {_name_key(name) for name in self.session.scalars(statement) if name}
        if _name_key(base_name) not in existing:
            return base_name

        suffix = 1
        while True:
            candidate = _fit_campaign_name_with_suffix(base_name, suffix)
            if _name_key(candidate) not in existing:
                return candidate
            suffix += 1

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


def _collapse_spaces(value: str) -> str:
    return " ".join(value.split())


def _name_key(value: str) -> str:
    return _collapse_spaces(value).casefold()


def _fit_campaign_name(value: str, max_length: int = 255) -> str:
    cleaned = _collapse_spaces(value)
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[:max_length].rstrip()


def _fit_campaign_name_with_suffix(value: str, suffix: int, max_length: int = 255) -> str:
    suffix_text = f" {suffix}"
    base = _fit_campaign_name(value, max_length=max_length - len(suffix_text))
    return f"{base}{suffix_text}"
