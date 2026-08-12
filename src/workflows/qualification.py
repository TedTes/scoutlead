from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.repository import LeadRepository
from leads.schemas import LeadRead, LeadStatus, QualificationResult
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from prompts.qualification import fallback_qualification, qualification_prompt


class QualificationWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        llm: LLMClient,
    ) -> None:
        self.campaigns = campaigns
        self.leads = leads
        self.memory = memory
        self.llm = llm

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[LeadRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.QUALIFYING, stage=CampaignStage.QUALIFICATION
        )
        qualified: list[LeadRead] = []
        for lead_model in self.leads.list_by_campaign(campaign.id):
            lead = LeadRead.model_validate(lead_model)
            if lead.status != LeadStatus.RESEARCHED:
                continue
            fallback = fallback_qualification(product, lead)
            result = self.llm.generate_object(
                task="lead_qualification",
                system="Score the lead against explicit qualification criteria.",
                prompt=qualification_prompt(product, lead),
                response_model=QualificationResult,
                context={
                    "product": product.model_dump(mode="json"),
                    "lead": lead.model_dump(mode="json"),
                },
                fallback=fallback,
            )
            updated = LeadRead.model_validate(self.leads.attach_qualification(lead.id, result))
            qualified.append(updated)
            self.memory.create_observation(
                CampaignMemoryCreate(
                    product_id=product.id,
                    campaign_id=campaign.id,
                    type=ObservationType.LEAD_QUALITY,
                    content=f"{updated.company_name} scored {result.score}: {result.rationale}",
                    tags=["qualification", "qualified" if result.qualified else "disqualified"],
                    score_impact=result.score,
                )
            )
        return qualified
