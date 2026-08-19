from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadResearch, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from prompts.research import research_prompt
from tools.browser import DirectHttpBrowserTool


class ResearchWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        browser: DirectHttpBrowserTool,
        llm: LLMClient,
    ) -> None:
        self.campaigns = campaigns
        self.leads = leads
        self.memory = memory
        self.browser = browser
        self.llm = llm

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[LeadRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.RESEARCHING, stage=CampaignStage.RESEARCH
        )
        researched: list[LeadRead] = []
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status not in {LeadStatus.DISCOVERED, LeadStatus.RESEARCHING}:
                continue
            self.leads.update_status(lead.id, LeadStatus.RESEARCHING)
            inspection = self.browser.inspect(lead.website_url) if lead.website_url else None
            research = self.llm.generate_object(
                task="lead_research",
                system="Extract structured lead research from public evidence only.",
                prompt=research_prompt(product, lead, inspection),
                response_model=LeadResearch,
                context={
                    "product": product.model_dump(mode="json"),
                    "lead": lead.model_dump(mode="json"),
                    "inspection": inspection.model_dump(mode="json") if inspection else None,
                },
            )
            researched.append(LeadRead.model_validate(self.leads.attach_research(lead.id, research)))
        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Research completed for {len(researched)} leads.",
                tags=["research"],
            )
        )
        return researched
