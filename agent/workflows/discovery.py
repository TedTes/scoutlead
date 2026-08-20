from typing import Any, Callable

from agents.runner import BoundedAgentRunner, StopAction, ToolAction
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus, LeadSeedInput
from discovery.classifier import assess_discovery_candidate
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateCreate
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from tools.search import SearchResult, SearchTool


class DiscoveryWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        candidates: DiscoveryCandidateRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        search_tool: SearchTool,
        on_tool_start: Callable[[ToolAction, int], str | None] | None = None,
        on_tool_success: Callable[[str, Any], None] | None = None,
        on_tool_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.campaigns = campaigns
        self.candidates = candidates
        self.leads = leads
        self.memory = memory
        self.search_tool = search_tool
        self.on_tool_start = on_tool_start
        self.on_tool_success = on_tool_success
        self.on_tool_error = on_tool_error

    def run(self, product: ProductRead, campaign: CampaignRead) -> list[LeadRead]:
        self.campaigns.update_status(
            campaign.id, CampaignStatus.DISCOVERING, stage=CampaignStage.DISCOVERY
        )

        discovered: list[dict] = []
        for seed_data in campaign.discovery_seeds:
            seed = LeadSeedInput.model_validate(seed_data)
            lead = self.leads.create_from_seed(campaign.id, product.id, seed)
            discovered.append(LeadRead.model_validate(lead).model_dump(mode="json"))

        runner = BoundedAgentRunner()
        sources = product.preferred_discovery_sources

        def decide(state: dict, iteration: int):
            if state["source_index"] >= len(sources):
                return StopAction("no more configured discovery sources")
            source = sources[state["source_index"]]
            resolved_query = self.search_tool.build_query(
                product=product,
                campaign=campaign,
                source=source,
            )
            return ToolAction(
                tool_name="search",
                reason=f"search configured source {source.type.value}:{source.value}",
                args={
                    "product": product.model_dump(mode="json"),
                    "campaign": campaign.model_dump(mode="json"),
                    "source": source.model_dump(mode="json"),
                    "resolved_query": resolved_query,
                    "limit": min(source.limit or campaign.max_leads, campaign.max_leads),
                },
            )

        def observe(state: dict, action: ToolAction, observation, iteration: int):
            enriched_rows = []
            for row in observation:
                enriched = dict(row)
                enriched["discovery_query"] = action.args["resolved_query"]
                enriched_rows.append(enriched)
            return {
                "source_index": state["source_index"] + 1,
                "results": [*state["results"], *enriched_rows],
            }

        result = runner.run(
            goal=f"Discover leads for {product.product_name}",
            initial_state={"source_index": 0, "results": []},
            max_iterations=max(1, len(sources)),
            allowed_tools={"search"},
            tools=[self.search_tool],
            decide=decide,
            observe=observe,
            on_tool_start=self.on_tool_start,
            on_tool_success=self.on_tool_success,
            on_tool_error=self.on_tool_error,
        )

        for row in result.state["results"]:
            search_result = SearchResult.model_validate(row)
            assessment = assess_discovery_candidate(search_result, product)
            candidate = self.candidates.create(
                DiscoveryCandidateCreate(
                    campaign_id=campaign.id,
                    product_id=product.id,
                    query=str(row.get("discovery_query") or search_result.raw.get("query") or ""),
                    title=search_result.title,
                    url=search_result.url,
                    snippet=search_result.snippet,
                    geography=search_result.geography,
                    contact_email=search_result.contact_email,
                    source=search_result.source,
                    raw=row,
                    candidate_type=assessment.candidate_type,
                    confidence=assessment.confidence,
                    rejection_reason=assessment.rejection_reason,
                )
            )
            if not assessment.is_promotable or len(discovered) >= campaign.max_leads:
                continue
            lead = self.leads.create_from_candidate(candidate)
            self.candidates.mark_promoted(candidate.id, lead.id)
            discovered.append(LeadRead.model_validate(lead).model_dump(mode="json"))

        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Discovery produced {len(discovered)} leads.",
                tags=["discovery", product.target_customer],
            )
        )
        return [LeadRead.model_validate(row) for row in discovered]
