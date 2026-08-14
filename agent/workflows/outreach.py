from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from messages.repository import MessageRepository
from messages.schemas import MessageRead, MessageStatus, OutreachDraft
from products.schemas import ProductRead
from prompts.outreach import fallback_outreach, outreach_prompt


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
            if self.messages.has_draft_for_lead(lead.id, channel.value):
                continue
            fallback = fallback_outreach(product, lead, channel)
            draft = self.llm.generate_object(
                task="outreach_draft",
                system="Draft concise validation outreach for human approval.",
                prompt=outreach_prompt(product, lead, channel),
                response_model=OutreachDraft,
                context={
                    "product": product.model_dump(mode="json"),
                    "lead": lead.model_dump(mode="json"),
                },
                fallback=fallback,
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
