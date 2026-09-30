import httpx

from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadResearch, LeadStatus
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from prompts.research import research_prompt
from evaluation.lead_scoring import build_cached_lead_research
from evaluation.digital_opportunity import (
    has_minimum_opportunity,
    source_inputs_require_digital_opportunity,
)
from shared.logger import get_logger
from tools.browser import DirectHttpBrowserTool


logger = get_logger(__name__)


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
            if (
                source_inputs_require_digital_opportunity(campaign.source_inputs)
                and not has_minimum_opportunity(lead.raw_sources, minimum="moderate")
            ):
                continue
            self.leads.update_status(lead.id, LeadStatus.RESEARCHING)
            inspection = self.browser.inspect(lead.website_url) if lead.website_url else None
            try:
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
            except httpx.TransportError as exc:
                logger.warning(
                    "lead_research_transport_failed lead_id=%s error=%s",
                    lead.id,
                    exc,
                )
                research = build_cached_lead_research(
                    product=product,
                    lead=lead,
                    row={
                        "source": lead.source,
                        "url": lead.website_url,
                        "snippet": lead.description,
                        "raw": {"sources": lead.raw_sources},
                    },
                    confidence=35,
                )
            scraped_emails = inspection.emails if inspection else []
            candidates = list(
                dict.fromkeys([*scraped_emails, *([research.contact_email] if research.contact_email else [])])
            )
            research = research.model_copy(update={"contact_candidates": candidates})
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
