from typing import Any, Callable

from agents.runner import BoundedAgentRunner, StopAction, ToolAction
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead, CampaignSourceSlot
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
from tools.source_registry import CampaignSourceTool, SourceAdapterRegistry


class DiscoveryWorkflow:
    def __init__(
        self,
        *,
        campaigns: CampaignRepository,
        campaign_sources: CampaignSourceRepository,
        candidates: DiscoveryCandidateRepository,
        leads: LeadRepository,
        memory: MemoryRepository,
        search_tool: SearchTool,
        google_places_api_key: str | None = None,
        google_places_api_endpoint: str | None = None,
        apify_api_token: str | None = None,
        apify_api_base_url: str | None = None,
        apify_source_provider_id: str = "apify_actor",
        apify_actor_id: str | None = None,
        apify_actor_input_template: str | None = None,
        apify_actor_result_mapping: str | None = None,
        apify_actor_max_charge_usd: float | None = None,
        timeout_seconds: float = 20.0,
        on_tool_start: Callable[[ToolAction, int], str | None] | None = None,
        on_tool_success: Callable[[str, Any], None] | None = None,
        on_tool_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.campaigns = campaigns
        self.campaign_sources = campaign_sources
        self.candidates = candidates
        self.leads = leads
        self.memory = memory
        self.search_tool = search_tool
        self.google_places_api_key = google_places_api_key
        self.google_places_api_endpoint = google_places_api_endpoint
        self.apify_api_token = apify_api_token
        self.apify_api_base_url = apify_api_base_url
        self.apify_source_provider_id = apify_source_provider_id
        self.apify_actor_id = apify_actor_id
        self.apify_actor_input_template = apify_actor_input_template
        self.apify_actor_result_mapping = apify_actor_result_mapping
        self.apify_actor_max_charge_usd = apify_actor_max_charge_usd
        self.timeout_seconds = timeout_seconds
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
        sources = [
            CampaignSourceRead.model_validate(source)
            for source in self.campaign_sources.list_by_campaign(
                campaign.id,
                slot=CampaignSourceSlot.DISCOVERY,
                enabled_only=True,
            )
        ]
        source_tool = CampaignSourceTool(
            SourceAdapterRegistry(
                search_tool=self.search_tool,
                google_places_api_key=self.google_places_api_key,
                google_places_api_endpoint=self.google_places_api_endpoint,
                apify_api_token=self.apify_api_token,
                apify_api_base_url=self.apify_api_base_url,
                apify_source_provider_id=self.apify_source_provider_id,
                apify_actor_id=self.apify_actor_id,
                apify_actor_input_template=self.apify_actor_input_template,
                apify_actor_result_mapping=self.apify_actor_result_mapping,
                apify_actor_max_charge_usd=self.apify_actor_max_charge_usd,
                timeout_seconds=self.timeout_seconds,
            )
        )

        def decide(state: dict, iteration: int):
            if state["source_index"] >= len(sources):
                return StopAction("no more campaign discovery sources")
            source = sources[state["source_index"]]
            return ToolAction(
                tool_name=source_tool.name,
                reason=(
                    f"run campaign source {source.provider_id} for {source.slot.value}"
                ),
                args={
                    "source": source.model_dump(mode="json"),
                    "context": {
                        "product": product.model_dump(mode="json"),
                        "campaign": campaign.model_dump(mode="json"),
                    },
                },
            )

        def observe(state: dict, action: ToolAction, observation, iteration: int):
            enriched_rows = []
            tool_data = observation.get("data", []) if isinstance(observation, dict) else []
            source = sources[state["source_index"]]
            for row in tool_data:
                enriched = dict(row)
                enriched["discovery_query"] = source.input.get("query") or ""
                enriched["campaign_source_id"] = source.id
                enriched["provider_id"] = source.provider_id
                enriched_rows.append(enriched)
            return {
                "source_index": state["source_index"] + 1,
                "results": [*state["results"], *enriched_rows],
            }

        result = runner.run(
            goal=f"Discover leads for {product.product_name}",
            initial_state={"source_index": 0, "results": []},
            max_iterations=max(1, len(sources)),
            allowed_tools={source_tool.name},
            tools=[source_tool],
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
