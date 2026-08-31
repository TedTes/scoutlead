from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import MessageModel
from messages.schemas import MessageApproval, MessageStatus, MessageUpdate, OutreachDraft
from messages.state import assert_message_transition
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_draft(
        self, campaign_id: str, product_id: str, lead_id: str, draft: OutreachDraft
    ) -> MessageModel:
        data = draft.model_dump(mode="json")
        model = MessageModel(
            id=new_id("message"),
            campaign_id=campaign_id,
            product_id=product_id,
            lead_id=lead_id,
            status=MessageStatus.PENDING_APPROVAL.value,
            **data,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return model

    def get(self, message_id: str) -> MessageModel:
        model = self.session.get(MessageModel, message_id)
        if model is None:
            raise NotFoundError("message not found", {"message_id": message_id})
        return model

    def list_by_campaign(self, campaign_id: str) -> list[MessageModel]:
        statement = (
            select(MessageModel)
            .where(MessageModel.campaign_id == campaign_id)
            .order_by(MessageModel.created_at)
        )
        return list(self.session.scalars(statement))

    def list_by_lead(self, lead_id: str) -> list[MessageModel]:
        statement = select(MessageModel).where(MessageModel.lead_id == lead_id).order_by(MessageModel.created_at.desc())
        return list(self.session.scalars(statement))

    def latest_for_lead(self, lead_id: str, channel: str | None = None) -> MessageModel | None:
        statement = select(MessageModel).where(MessageModel.lead_id == lead_id)
        if channel is not None:
            statement = statement.where(MessageModel.channel == channel)
        statement = statement.order_by(MessageModel.created_at.desc())
        return self.session.scalars(statement).first()

    def has_draft_for_lead(self, lead_id: str, channel: str | None = None) -> bool:
        messages = self.list_by_lead(lead_id)
        return any(channel is None or message.channel == channel for message in messages)

    def approve(self, message_id: str, approval: MessageApproval) -> MessageModel:
        model = self.get(message_id)
        assert_message_transition(MessageStatus(model.status), MessageStatus.APPROVED)
        model.status = MessageStatus.APPROVED.value
        model.approval = {
            **approval.model_dump(mode="json"),
            "approved_at": utcnow().isoformat(),
        }
        self.session.commit()
        self.session.refresh(model)
        return model

    def update_draft(self, message_id: str, update: MessageUpdate) -> MessageModel:
        model = self.get(message_id)
        if MessageStatus(model.status) not in {MessageStatus.DRAFT, MessageStatus.PENDING_APPROVAL}:
            raise ConflictError(
                "only draft or pending approval messages can be edited",
                {"message_id": message_id, "status": model.status},
            )
        data = update.model_dump(mode="json", exclude_unset=True)
        for field, value in data.items():
            setattr(model, field, value)
        self.session.commit()
        self.session.refresh(model)
        return model

    def set_status(
        self,
        message_id: str,
        status: MessageStatus,
        *,
        provider_message_id: str | None = None,
        sent_at=None,
        failure_reason: str | None = None,
    ) -> MessageModel:
        model = self.get(message_id)
        assert_message_transition(MessageStatus(model.status), status)
        model.status = status.value
        if provider_message_id is not None:
            model.provider_message_id = provider_message_id
        if sent_at is not None:
            model.sent_at = sent_at
        if failure_reason is not None:
            model.failure_reason = failure_reason
        self.session.commit()
        self.session.refresh(model)
        return model
