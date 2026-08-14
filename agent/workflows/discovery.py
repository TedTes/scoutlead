from typing import Any, Callable

from agents.runner import BoundedAgentRunner, StopAction, ToolAction
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus, LeadSeedInput
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from products.schemas import ProductRead
from tools.search import SearchTool


class DiscoveryWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        search_tool: SearchTool,
        on_tool_start: Callable[[ToolAction, int], str | None] | None = None,
        on_tool_success: Callable[[str, Any], None] | None = None,
        on_tool_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.campaigns = campaigns
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
            if len(state["results"]) >= campaign.max_leads:
                return StopAction("lead limit reached")
            if state["source_index"] >= len(sources):
                return StopAction("no more configured discovery sources")
            source = sources[state["source_index"]]
            return ToolAction(
                tool_name="search",
                reason=f"search configured source {source.type.value}:{source.value}",
                args={
                    "product": product.model_dump(mode="json"),
                    "campaign": campaign.model_dump(mode="json"),
                    "source": source.model_dump(mode="json"),
                    "limit": min(source.limit or campaign.max_leads, campaign.max_leads),
                },
            )

        def observe(state: dict, action: ToolAction, observation, iteration: int):
            return {
                "source_index": state["source_index"] + 1,
                "results": [*state["results"], *observation][: campaign.max_leads],
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
            lead = self.leads.create_from_search_result(campaign.id, product.id, row)
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
