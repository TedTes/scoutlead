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
from db.models import ConversationEventModel, ConversationModel
from shared.errors import NotFoundError
from shared.utils import new_id, utcnow


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, conversation_id: str) -> ConversationModel:
        model = self.session.get(ConversationModel, conversation_id)
        if model is None:
            raise NotFoundError("conversation not found", {"conversation_id": conversation_id})
        return model

    def list_by_campaign(self, campaign_id: str) -> list[ConversationModel]:
        statement = (
            select(ConversationModel)
            .where(ConversationModel.campaign_id == campaign_id)
            .order_by(ConversationModel.created_at)
        )
        return list(self.session.scalars(statement))

    def get_or_create(
        self, campaign_id: str, product_id: str, lead_id: str
    ) -> ConversationModel:
        statement = select(ConversationModel).where(
            ConversationModel.campaign_id == campaign_id,
            ConversationModel.lead_id == lead_id,
        )
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
