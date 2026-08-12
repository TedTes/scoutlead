from datetime import datetime

from sqlalchemy.orm import Session

from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignStatus
from conversations.repository import ConversationRepository
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from messages.repository import MessageRepository
from messages.schemas import MessageApproval, MessageRead, MessageStatus, MessageUpdate
from products.repository import ProductRepository
from products.schemas import ProductRead
from tools.email import EmailTool


class MessageService:
    def __init__(self, *, session: Session, email: EmailTool) -> None:
        self.session = session
        self.email = email
        self.products = ProductRepository(session)
        self.campaigns = CampaignRepository(session)
        self.leads = LeadRepository(session)
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)

    def approve(self, message_id: str, approval: MessageApproval) -> MessageRead:
        message = self.messages.approve(message_id, approval)
        self.leads.update_status(message.lead_id, LeadStatus.APPROVED)
        return MessageRead.model_validate(message)

    def update(self, message_id: str, update: MessageUpdate) -> MessageRead:
        return MessageRead.model_validate(self.messages.update_draft(message_id, update))

    def cancel(self, message_id: str) -> MessageRead:
        message = self.messages.set_status(message_id, MessageStatus.CANCELLED)
        return MessageRead.model_validate(message)

    def send(self, message_id: str) -> MessageRead:
        message = MessageRead.model_validate(self.messages.get(message_id))
        product = ProductRead.model_validate(self.products.get(message.product_id))
        lead = LeadRead.model_validate(self.leads.get(message.lead_id))
        campaign = self.campaigns.get(message.campaign_id)

        if campaign.status == CampaignStatus.AWAITING_APPROVAL.value:
            self.campaigns.update_status(message.campaign_id, CampaignStatus.SENDING)

        result = self.email.send(product=product, lead=lead, message=message)
        sent_at = datetime.fromisoformat(result.sent_at)
        updated = self.messages.set_status(
            message_id,
            MessageStatus.SENT,
            provider_message_id=result.provider_message_id,
            sent_at=sent_at,
        )
        self.leads.update_status(message.lead_id, LeadStatus.SENT)
        conversation = self.conversations.get_or_create(
            message.campaign_id, message.product_id, message.lead_id
        )
        self.conversations.add_outbound_event(conversation.id, message.id, message.body)

        campaign = self.campaigns.get(message.campaign_id)
        if campaign.status == CampaignStatus.SENDING.value:
            self.campaigns.update_status(message.campaign_id, CampaignStatus.TRACKING)

        return MessageRead.model_validate(updated)
