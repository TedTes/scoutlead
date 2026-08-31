from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.goal import goal_policy
from campaigns.schemas import CampaignGoalType
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.policy import can_shortlist_lead, is_outreach_ready
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus, LeadUpdate
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from messages.repository import MessageRepository
from messages.schemas import MessageRead, MessageStatus, OutreachDraft
from products.schemas import ProductRead
from prompts.outreach_learn import outreach_learn_prompt
from prompts.outreach_sell import outreach_sell_prompt


class OutreachWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        messages: MessageRepository,
        memory: MemoryRepository,
        llm: LLMClient,
    ) -> None:
        self.campaigns = campaigns
        self.leads = leads
        self.messages = messages
        self.memory = memory
        self.llm = llm

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[MessageRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.DRAFTING_OUTREACH, stage=CampaignStage.OUTREACH
        )
        drafts: list[MessageRead] = []
        channel = campaign.channels[0]
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status != LeadStatus.QUALIFIED:
                continue
            if not lead.shortlisted_at and can_shortlist_lead(
                review_status=lead.review_status,
                qualification=lead.qualification,
            ):
                lead = LeadRead.model_validate(self.leads.update(lead.id, LeadUpdate(shortlisted=True)))
            if not is_outreach_ready(lead):
                continue
            if self.messages.has_draft_for_lead(lead.id, channel.value):
                continue
            policy = goal_policy(campaign.goal_type)
            if policy.goal_type == CampaignGoalType.SELL:
                prompt = outreach_sell_prompt(product, lead, channel)
                system = "Draft concise sales outreach for human approval."
            else:
                prompt = outreach_learn_prompt(product, lead, channel)
                system = "Draft customer-discovery outreach for human approval."
            draft = self.llm.generate_object(
                task="outreach_draft",
                system=system,
                prompt=prompt,
                response_model=OutreachDraft,
                context={
                    "product": product.model_dump(mode="json"),
                    "lead": lead.model_dump(mode="json"),
                },
            )
            message = self.messages.create_draft(campaign.id, product.id, lead.id, draft)
            self.leads.update_status(lead.id, LeadStatus.AWAITING_APPROVAL)
            drafts.append(MessageRead.model_validate(message))

        pending_approval_count = sum(
            1
            for message in self.messages.list_by_campaign(campaign.id)
            if message.status == MessageStatus.PENDING_APPROVAL.value
        )
        if pending_approval_count > 0:
            self.campaigns.update_status(
                campaign.id, CampaignStatus.AWAITING_APPROVAL, stage=CampaignStage.OUTREACH
            )
        else:
            self.campaigns.update_status(
                campaign.id, CampaignStatus.COMPLETED, stage=CampaignStage.COMPLETE
            )
        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.OUTREACH_VARIANT,
                content=(
                    f"Drafted {len(drafts)} outreach messages for approval. "
                    f"{pending_approval_count} messages are pending approval."
                ),
                tags=["outreach", "pending_approval" if pending_approval_count else "no_pending_approval"],
            )
        )
        return drafts
