from datetime import datetime

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.goal import goal_policy
from campaigns.schemas import CampaignGoalType, CampaignRead, CampaignStatus, OutreachChannel
from conversations.repository import ConversationRepository
from leads.policy import (
    is_draftable_lead,
    is_outreach_ready,
    is_reachable_lead,
    is_verified_lead,
    lead_email,
)
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from messages.repository import MessageRepository
from messages.schemas import MessageApproval, MessageRead, MessageStatus, MessageUpdate, OutreachDraft
from messages.state import assert_send_allowed
from prompts.outreach_learn import outreach_learn_prompt
from prompts.outreach_sell import outreach_sell_prompt
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ConflictError
from tools.email import EmailTool


class MessageService:
    def __init__(self, *, session: Session, email: EmailTool, llm: LLMClient | None = None) -> None:
        self.session = session
        self.email = email.bind_session(session)
        self.llm = llm
        self.products = ProductRepository(session)
        self.campaigns = CampaignRepository(session)
        self.leads = LeadRepository(session)
        self.messages = MessageRepository(session)
        self.conversations = ConversationRepository(session)

    def create_outreach_draft_for_lead(self, lead_id: str) -> MessageRead:
        if self.llm is None:
            raise ConflictError(
                "outreach draft generation is not configured",
                {"lead_id": lead_id, "user_message": "Draft generation is not configured for this environment."},
            )
        lead = LeadRead.model_validate(self.leads.get(lead_id))
        if not lead.shortlisted_at:
            raise ConflictError(
                "lead must be shortlisted before generating outreach",
                {"lead_id": lead_id, "user_message": "Shortlist this contact before generating outreach."},
            )
        if not is_outreach_ready(lead):
            raise ConflictError(
                "lead needs a positive fit decision before outreach",
                {
                    "lead_id": lead_id,
                    "review_status": lead.review_status.value,
                    "user_message": "Mark this contact as Good fit or Maybe before generating outreach.",
                },
            )
        if not is_reachable_lead(lead):
            raise ConflictError(
                "lead needs a reachable email before outreach",
                {"lead_id": lead_id, "user_message": "Find an email before generating outreach."},
            )
        if not is_verified_lead(lead):
            raise ConflictError(
                "lead must be verified before outreach",
                {
                    "lead_id": lead_id,
                    "verification_status": lead.verification_status.value,
                    "user_message": "Verify this contact before generating outreach.",
                },
            )

        campaign = CampaignRead.model_validate(self.campaigns.get(lead.campaign_id))
        product = ProductRead.model_validate(self.products.get(lead.product_id))
        channel = _message_channel(campaign)
        existing = self.messages.latest_for_lead(lead.id, channel.value)
        if existing and MessageStatus(existing.status) not in {MessageStatus.CANCELLED, MessageStatus.FAILED}:
            return MessageRead.model_validate(existing)

        policy = goal_policy(campaign.goal_type)
        if policy.goal_type == CampaignGoalType.SELL:
            system = "Draft concise sales outreach for human approval."
            prompt = outreach_sell_prompt(product, lead, channel)
        else:
            system = "Draft customer-discovery outreach for human approval."
            prompt = outreach_learn_prompt(product, lead, channel)
        draft = self.llm.generate_object(
            task="outreach_draft",
            system=system,
            prompt=prompt,
            response_model=OutreachDraft,
            context={
                "product": product.model_dump(mode="json"),
                "lead": lead.model_dump(mode="json"),
                "campaign": campaign.model_dump(mode="json"),
            },
        )
        message = self.messages.create_draft(campaign.id, product.id, lead.id, draft)
        self.leads.update_status(lead.id, LeadStatus.AWAITING_APPROVAL)
        return MessageRead.model_validate(message)

    def create_outreach_drafts_for_run(self, campaign_id: str) -> list[MessageRead]:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        created: list[MessageRead] = []
        channel = _message_channel(campaign)
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if not is_draftable_lead(lead):
                continue
            existing = self.messages.latest_for_lead(lead.id, channel.value)
            if existing and MessageStatus(existing.status) not in {MessageStatus.CANCELLED, MessageStatus.FAILED}:
                continue
            created.append(self.create_outreach_draft_for_lead(lead.id))
        return created

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

        assert_send_allowed(message.status)
        if not is_outreach_ready(lead):
            raise ConflictError(
                "lead needs a positive fit decision before sending",
                {
                    "lead_id": lead.id,
                    "review_status": lead.review_status.value,
                    "user_message": "Shortlist a Good fit or Maybe contact before sending.",
                },
            )
        if not is_reachable_lead(lead):
            raise ConflictError(
                "lead needs a reachable email before sending",
                {"lead_id": lead.id, "user_message": "Find an email before sending."},
            )
        if not is_verified_lead(lead):
            raise ConflictError(
                "lead must be verified before sending",
                {
                    "lead_id": lead.id,
                    "verification_status": lead.verification_status.value,
                    "user_message": "Verify this contact before sending.",
                },
            )
        email = lead_email(lead)
        if email and lead.contact_email != email:
            lead.contact_email = email
        if campaign.status == CampaignStatus.AWAITING_APPROVAL.value:
            self.campaigns.update_status(message.campaign_id, CampaignStatus.SENDING)

        try:
            result = self.email.send(product=product, lead=lead, message=message)
        except Exception as exc:
            self.messages.set_status(
                message_id,
                MessageStatus.FAILED,
                failure_reason=str(exc),
            )
            raise
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


def _message_channel(campaign: CampaignRead) -> OutreachChannel:
    if not campaign.channels:
        return OutreachChannel.EMAIL
    value = campaign.channels[0]
    return value if isinstance(value, OutreachChannel) else OutreachChannel(str(value))
