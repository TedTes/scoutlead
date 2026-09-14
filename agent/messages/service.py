import re
from datetime import datetime

from sqlalchemy.orm import Session

from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.goal import goal_policy
from campaigns.schemas import CampaignGoalType, CampaignRead, CampaignStatus, OutreachChannel
from conversations.repository import ConversationRepository
from conversations.schemas import FollowUpAction, ResponseClassification, ResponseIntent
from leads.policy import (
    can_shortlist_lead,
    contact_block_reason,
    is_draftable_lead,
    is_contact_blocked_lead,
    is_outreach_ready,
    is_reachable_lead,
    is_verified_lead,
    lead_email,
)
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus, LeadUpdate
from messages.repository import MessageRepository
from messages.schemas import (
    CampaignMessageApproval,
    CampaignMessageBatchResult,
    CampaignMessageSend,
    CampaignMessageSkip,
    CampaignOutreachAudience,
    CampaignOutreachDraftCreate,
    MessageApproval,
    MessageRead,
    MessageReplyMark,
    MessageStatus,
    MessageUpdate,
    OutreachDraft,
)
from messages.state import assert_send_allowed
from prompts.outreach_learn import outreach_learn_prompt
from prompts.outreach_sell import outreach_sell_prompt
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ConflictError, SoutleadError
from tools.email import EmailTool


_TEMPLATE_TOKEN_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")
_REUSABLE_MESSAGE_STATUSES = {
    MessageStatus.PENDING_APPROVAL,
    MessageStatus.APPROVED,
    MessageStatus.SENT,
}


class MessageService:
    def __init__(
        self,
        *,
        session: Session,
        email: EmailTool,
        llm: LLMClient | None = None,
        workspace_id: str | None = None,
    ) -> None:
        self.session = session
        self.email = email.bind_session(session)
        self.llm = llm
        self.products = ProductRepository(session, workspace_id=workspace_id)
        self.campaigns = CampaignRepository(session, workspace_id=workspace_id)
        self.leads = LeadRepository(session, workspace_id=workspace_id)
        self.messages = MessageRepository(session, workspace_id=workspace_id)
        self.conversations = ConversationRepository(session, workspace_id=workspace_id)

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
        if is_contact_blocked_lead(lead):
            raise ConflictError(
                "lead is blocked from outreach",
                {
                    "lead_id": lead_id,
                    "contact_policy_status": lead.contact_policy_status.value,
                    "user_message": contact_block_reason(lead),
                },
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

    def create_campaign_outreach_drafts(
        self,
        campaign_id: str,
        draft_request: CampaignOutreachDraftCreate,
    ) -> CampaignMessageBatchResult:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        channel = _message_channel(campaign)
        candidates = self._campaign_outreach_candidates(campaign, draft_request)
        messages: list[MessageRead] = []
        skipped: list[CampaignMessageSkip] = []
        created_count = 0
        reused_count = 0

        for lead in candidates:
            prepared_lead, reason = self._prepare_campaign_outreach_lead(
                lead,
                allow_auto_shortlist=draft_request.audience != CampaignOutreachAudience.READY_SHORTLIST,
            )
            if reason:
                skipped.append(_skip_for_lead(lead, reason))
                continue

            existing = self.messages.latest_for_lead(prepared_lead.id, channel.value)
            if existing and MessageStatus(existing.status) in _REUSABLE_MESSAGE_STATUSES:
                messages.append(MessageRead.model_validate(existing))
                reused_count += 1
                continue

            draft = _campaign_template_draft(
                product=product,
                lead=prepared_lead,
                channel=channel,
                draft_request=draft_request,
            )
            message = self.messages.create_draft(campaign.id, product.id, prepared_lead.id, draft)
            self.leads.update_status(prepared_lead.id, LeadStatus.AWAITING_APPROVAL)
            messages.append(MessageRead.model_validate(message))
            created_count += 1

        return CampaignMessageBatchResult(
            messages=messages,
            skipped=skipped,
            created_count=created_count,
            reused_count=reused_count,
        )

    def approve_campaign_messages(
        self,
        campaign_id: str,
        approval: CampaignMessageApproval,
    ) -> CampaignMessageBatchResult:
        self.campaigns.get(campaign_id)
        message_models = self._campaign_message_selection(
            campaign_id,
            approval.message_ids,
            default_status=MessageStatus.PENDING_APPROVAL,
        )
        messages: list[MessageRead] = []
        skipped: list[CampaignMessageSkip] = []
        approved_count = 0

        for message_model in message_models:
            message = MessageRead.model_validate(message_model)
            if message.status == MessageStatus.APPROVED:
                messages.append(message)
                continue
            if message.status != MessageStatus.PENDING_APPROVAL:
                skipped.append(_skip_for_message(message, "Only pending approval drafts can be approved."))
                continue
            approved = self.approve(
                message.id,
                MessageApproval(approved_by=approval.approved_by, notes=approval.notes),
            )
            messages.append(approved)
            approved_count += 1

        return CampaignMessageBatchResult(
            messages=messages,
            skipped=skipped,
            approved_count=approved_count,
        )

    def send_campaign_messages(
        self,
        campaign_id: str,
        send_request: CampaignMessageSend,
    ) -> CampaignMessageBatchResult:
        self.campaigns.get(campaign_id)
        message_models = self._campaign_message_selection(
            campaign_id,
            send_request.message_ids,
            default_status=MessageStatus.APPROVED,
        )
        messages: list[MessageRead] = []
        skipped: list[CampaignMessageSkip] = []
        sent_count = 0
        failed_count = 0

        for message_model in message_models:
            message = MessageRead.model_validate(message_model)
            if message.status == MessageStatus.SENT:
                messages.append(message)
                continue
            if message.status != MessageStatus.APPROVED:
                skipped.append(_skip_for_message(message, "Approve this draft before sending."))
                continue
            try:
                sent = self.send(message.id)
            except Exception as exc:
                skipped.append(_skip_for_message(message, _send_failure_reason(exc)))
                failed_count += 1
                continue
            messages.append(sent)
            sent_count += 1

        return CampaignMessageBatchResult(
            messages=messages,
            skipped=skipped,
            sent_count=sent_count,
            failed_count=failed_count,
        )

    def approve(self, message_id: str, approval: MessageApproval) -> MessageRead:
        message = self.messages.approve(message_id, approval)
        self.leads.update_status(message.lead_id, LeadStatus.APPROVED)
        return MessageRead.model_validate(message)

    def update(self, message_id: str, update: MessageUpdate) -> MessageRead:
        return MessageRead.model_validate(self.messages.update_draft(message_id, update))

    def cancel(self, message_id: str) -> MessageRead:
        message = self.messages.set_status(message_id, MessageStatus.CANCELLED)
        return MessageRead.model_validate(message)

    def mark_replied(self, message_id: str, reply: MessageReplyMark) -> MessageRead:
        message = MessageRead.model_validate(self.messages.get(message_id))
        updated = self.messages.set_status(message_id, MessageStatus.REPLIED)
        self.leads.update_status(message.lead_id, LeadStatus.RESPONDED)
        conversation = self.conversations.get_or_create(
            message.campaign_id, message.product_id, message.lead_id
        )
        self.conversations.add_inbound_event(
            conversation.id,
            reply.body or "Marked as replied manually.",
            ResponseClassification(
                intent=ResponseIntent.UNKNOWN,
                confidence=100,
                rationale="Marked as replied manually by the operator.",
                follow_up_action=FollowUpAction.MANUAL_REVIEW,
            ),
        )
        return MessageRead.model_validate(updated)

    def send(self, message_id: str) -> MessageRead:
        message = MessageRead.model_validate(self.messages.get(message_id))
        product = ProductRead.model_validate(self.products.get(message.product_id))
        lead = LeadRead.model_validate(self.leads.get(message.lead_id))
        campaign = self.campaigns.get(message.campaign_id)

        assert_send_allowed(message.status)
        if is_contact_blocked_lead(lead):
            raise ConflictError(
                "lead is blocked from outreach",
                {
                    "lead_id": lead.id,
                    "contact_policy_status": lead.contact_policy_status.value,
                    "user_message": contact_block_reason(lead),
                },
            )
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
        try:
            result = self.email.send(product=product, lead=lead, message=message)
        except Exception as exc:
            failure_reason = _send_failure_reason(exc)
            self.messages.set_status(
                message_id,
                MessageStatus.FAILED,
                failure_reason=failure_reason,
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
        self.leads.mark_contacted(message.lead_id, sent_at)
        conversation = self.conversations.get_or_create(
            message.campaign_id, message.product_id, message.lead_id
        )
        self.conversations.add_outbound_event(conversation.id, message.id, message.body)

        campaign = self.campaigns.get(message.campaign_id)
        if campaign.status in {CampaignStatus.AWAITING_APPROVAL.value, CampaignStatus.SENDING.value}:
            self.campaigns.update_status(message.campaign_id, CampaignStatus.TRACKING)

        return MessageRead.model_validate(updated)

    def _campaign_outreach_candidates(
        self,
        campaign: CampaignRead,
        draft_request: CampaignOutreachDraftCreate,
    ) -> list[LeadRead]:
        leads = [LeadRead.model_validate(model) for model in self.leads.list_by_campaign(campaign.id)]
        if draft_request.audience == CampaignOutreachAudience.SELECTED:
            if not draft_request.lead_ids:
                raise ConflictError(
                    "selected audience requires at least one lead",
                    {"user_message": "Select at least one contact before preparing campaign outreach."},
                )
            by_id = {lead.id: lead for lead in leads}
            missing_ids = [lead_id for lead_id in draft_request.lead_ids if lead_id not in by_id]
            if missing_ids:
                raise ConflictError(
                    "selected leads are not part of this discovery run",
                    {"lead_ids": missing_ids},
                )
            return [by_id[lead_id] for lead_id in draft_request.lead_ids]
        return leads

    def _prepare_campaign_outreach_lead(
        self,
        lead: LeadRead,
        *,
        allow_auto_shortlist: bool,
    ) -> tuple[LeadRead, str | None]:
        if is_contact_blocked_lead(lead):
            return lead, contact_block_reason(lead)
        if not is_reachable_lead(lead):
            return lead, "Find a reachable email before preparing outreach."
        if not is_verified_lead(lead):
            return lead, "Verify the email before preparing outreach."
        if is_outreach_ready(lead):
            return lead, None
        if not allow_auto_shortlist:
            return lead, "Shortlist this contact before preparing outreach."
        if not can_shortlist_lead(review_status=lead.review_status, qualification=lead.qualification):
            return lead, "Mark this contact as Good fit or Maybe before preparing outreach."
        updated = self.leads.update(lead.id, LeadUpdate(shortlisted=True))
        return LeadRead.model_validate(updated), None

    def _campaign_message_selection(
        self,
        campaign_id: str,
        message_ids: list[str],
        *,
        default_status: MessageStatus,
    ):
        message_models = self.messages.list_by_campaign(campaign_id)
        if not message_ids:
            return [
                message_model
                for message_model in message_models
                if MessageStatus(message_model.status) == default_status
            ]
        by_id = {message_model.id: message_model for message_model in message_models}
        missing_ids = [message_id for message_id in message_ids if message_id not in by_id]
        if missing_ids:
            raise ConflictError(
                "selected messages are not part of this discovery run",
                {"message_ids": missing_ids},
            )
        return [by_id[message_id] for message_id in message_ids]


def _message_channel(campaign: CampaignRead) -> OutreachChannel:
    if not campaign.channels:
        return OutreachChannel.EMAIL
    value = campaign.channels[0]
    return value if isinstance(value, OutreachChannel) else OutreachChannel(str(value))


def _send_failure_reason(exc: Exception) -> str:
    if isinstance(exc, SoutleadError):
        user_message = exc.details.get("user_message")
        if isinstance(user_message, str) and user_message.strip():
            return user_message.strip()
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _campaign_template_draft(
    *,
    product: ProductRead,
    lead: LeadRead,
    channel: OutreachChannel,
    draft_request: CampaignOutreachDraftCreate,
) -> OutreachDraft:
    tokens = _campaign_template_tokens(product, lead)
    subject = _render_template(draft_request.subject, tokens) or draft_request.subject.strip()
    body = _render_template(draft_request.body, tokens) or draft_request.body.strip()
    return OutreachDraft(
        channel=channel,
        subject=_truncate_subject(subject),
        body=body,
        personalization_notes=_campaign_personalization_notes(lead),
        approach_tag=draft_request.approach_tag,
    )


def _render_template(template: str, tokens: dict[str, str]) -> str:
    def replace_token(match: re.Match[str]) -> str:
        return tokens.get(match.group(1).lower(), "")

    return _TEMPLATE_TOKEN_PATTERN.sub(replace_token, template).strip()


def _campaign_template_tokens(product: ProductRead, lead: LeadRead) -> dict[str, str]:
    geography = _first_text(
        lead.geography,
        lead.research.geography if lead.research else None,
        product.target_geography,
    )
    fit_reason = _first_text(
        lead.qualification.rationale if lead.qualification else None,
        lead.research.summary if lead.research else None,
        lead.description,
    )
    website_url = _first_text(lead.website_url, lead.research.website_url if lead.research else None)
    contact_name = _first_text(lead.research.contact_name if lead.research else None)
    return {
        "business_name": lead.company_name,
        "company_name": lead.company_name,
        "contact_name": contact_name or f"{lead.company_name} team",
        "recipient_name": contact_name or f"{lead.company_name} team",
        "geography": geography,
        "service_area": geography,
        "fit_reason": fit_reason,
        "website_url": website_url,
        "product_name": product.product_name,
        "product_description": product.product_description,
        "value_proposition": product.value_proposition,
        "problem": product.problem_being_solved,
        "outreach_objective": product.outreach_objective,
    }


def _campaign_personalization_notes(lead: LeadRead) -> list[str]:
    notes = [f"Personalized for {lead.company_name}."]
    geography = _first_text(lead.geography, lead.research.geography if lead.research else None)
    if geography:
        notes.append(f"Location: {geography}.")
    fit_reason = _first_text(
        lead.qualification.rationale if lead.qualification else None,
        lead.research.summary if lead.research else None,
        lead.description,
    )
    if fit_reason:
        notes.append(f"Fit reason: {_short_text(fit_reason)}")
    return notes


def _first_text(*values: str | None) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _short_text(value: str, limit: int = 160) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1].rstrip()}..."


def _truncate_subject(subject: str) -> str:
    return _short_text(subject, 500)


def _skip_for_lead(lead: LeadRead, reason: str) -> CampaignMessageSkip:
    return CampaignMessageSkip(lead_id=lead.id, company_name=lead.company_name, reason=reason)


def _skip_for_message(message: MessageRead, reason: str) -> CampaignMessageSkip:
    return CampaignMessageSkip(
        lead_id=message.lead_id,
        message_id=message.id,
        reason=reason,
    )
