from agents.llm import LLMClient
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from leads.repository import LeadRepository
from leads.policy import normalize_qualification_result
from leads.schemas import AgentFitStatus, LeadRead, LeadStatus, QualificationResult
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from prompts.qualification import (
    DISQUALIFYING_LEAD_TYPES,
    disqualified_by_research,
    qualification_prompt,
)


MIN_QUALIFICATION_SCORE = 65


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
            result = self.llm.generate_object(
                task="lead_qualification",
                system="Score the lead against explicit qualification criteria.",
                prompt=qualification_prompt(product, lead),
                response_model=QualificationResult,
                context={
                    "product": product.model_dump(mode="json"),
                    "lead": lead.model_dump(mode="json"),
                },
            )
            result = enforce_qualification_boundary(product, lead, result)
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


def enforce_qualification_boundary(
    product: ProductRead,
    lead: LeadRead,
    result: QualificationResult,
) -> QualificationResult:
    if lead.research and lead.research.disqualifiers:
        return disqualified_by_research(product, lead)

    if lead.research and lead.research.lead_type in DISQUALIFYING_LEAD_TYPES:
        lead_type = lead.research.lead_type.value.replace("_", " ")
        return disqualified_by_research(
            product,
            lead,
            reason=f"Lead was disqualified before outreach because it is classified as {lead_type}, not a target customer.",
            score=min(25, result.score),
        )

    if result.qualified and result.score < MIN_QUALIFICATION_SCORE:
        return result.model_copy(
            update={
                "qualified": False,
                "fit_status": AgentFitStatus.NOT_FIT,
                "rationale": (
                    f"{result.rationale} Disqualified because the score is below "
                    f"the {MIN_QUALIFICATION_SCORE} qualification threshold."
                ),
                "recommended_next_step": "Do not send outreach.",
            }
        )

    return normalize_qualification_result(result)
