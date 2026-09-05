from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from conversations.schemas import (
    ConversationStatus,
    EventDirection,
    FollowUpAction,
    ResponseClassification,
    ResponseIntent,
)
from db.models import ConversationEventModel, ConversationModel, ProductModel
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class ConversationRepository:
    def __init__(self, session: Session, *, workspace_id: str | None = None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def get(self, conversation_id: str) -> ConversationModel:
        model = self.session.scalar(
            self._scope(select(ConversationModel).where(ConversationModel.id == conversation_id))
        )
        if model is None:
            raise NotFoundError("conversation not found", {"conversation_id": conversation_id})
        return model

    def list_by_campaign(self, campaign_id: str) -> list[ConversationModel]:
        statement = (
            select(ConversationModel)
            .where(ConversationModel.campaign_id == campaign_id)
            .order_by(ConversationModel.created_at)
        )
        statement = self._scope(statement)
        return list(self.session.scalars(statement))

    def get_or_create(
        self, campaign_id: str, product_id: str, lead_id: str
    ) -> ConversationModel:
        self._assert_product_in_scope(product_id)
        statement = select(ConversationModel).where(
            ConversationModel.campaign_id == campaign_id,
            ConversationModel.lead_id == lead_id,
        )
        statement = self._scope(statement)
        existing = self.session.scalar(statement)
        if existing:
            return existing

        model = ConversationModel(
            id=new_id("conversation"),
            campaign_id=campaign_id,
            product_id=product_id,
            lead_id=lead_id,
            status=ConversationStatus.WAITING.value,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def add_outbound_event(
        self, conversation_id: str, message_id: str, body: str
    ) -> ConversationModel:
        return self._add_event(
            conversation_id=conversation_id,
            direction=EventDirection.OUTBOUND,
            body=body,
            message_id=message_id,
            status=ConversationStatus.WAITING,
        )

    def add_inbound_event(
        self, conversation_id: str, body: str, classification: ResponseClassification
    ) -> ConversationModel:
        status = self._status_for_classification(classification)
        return self._add_event(
            conversation_id=conversation_id,
            direction=EventDirection.INBOUND,
            body=body,
            classification=classification,
            status=status,
        )

    def add_manual_classification(
        self, conversation_id: str, classification: ResponseClassification
    ) -> ConversationModel:
        status = self._status_for_classification(classification)
        return self._add_event(
            conversation_id=conversation_id,
            direction=EventDirection.INTERNAL,
            body="Manual response classification override.",
            classification=classification,
            status=status,
        )

    def _add_event(
        self,
        *,
        conversation_id: str,
        direction: EventDirection,
        body: str,
        status: ConversationStatus,
        message_id: str | None = None,
        classification: ResponseClassification | None = None,
    ) -> ConversationModel:
        conversation = self.get(conversation_id)
        event = ConversationEventModel(
            id=new_id("event"),
            conversation_id=conversation_id,
            direction=direction.value,
            message_id=message_id,
            body=body,
            classification=classification.model_dump(mode="json") if classification else None,
            created_at=utcnow(),
        )
        conversation.status = status.value
        self.session.add(event)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def _scope(self, statement):
        if not self.workspace_id:
            return statement
        return statement.join(ProductModel, ConversationModel.product_id == ProductModel.id).where(
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

    @staticmethod
    def _status_for_classification(classification: ResponseClassification) -> ConversationStatus:
        if classification.follow_up_action == FollowUpAction.CLOSE:
            return ConversationStatus.CLOSED
        if classification.follow_up_action == FollowUpAction.MANUAL_REVIEW:
            return ConversationStatus.MANUAL_REVIEW
        if classification.intent in {
            ResponseIntent.INTERESTED,
            ResponseIntent.INTERVIEW_REQUEST,
            ResponseIntent.PRODUCT_TRIAL_INTEREST,
        }:
            return ConversationStatus.INTERESTED
        return ConversationStatus.OPEN
