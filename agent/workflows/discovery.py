from typing import Any, Callable

from agents.embeddings import EmbeddingClient, MissingEmbeddingClient
from agents.runner import BoundedAgentRunner, StopAction, ToolAction
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead, CampaignSourceSlot
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus, LeadSeedInput
from canonical.normalization import (
    external_id_from_raw,
    normalize_business_name,
    normalize_domain,
    normalize_phone,
    phone_from_raw,
)
from canonical.repository import CanonicalRepository
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
from territories.dedupe import exclude_previously_delivered_rows


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
        apify_sources: list[dict[str, Any]] | None = None,
        embedding: EmbeddingClient | None = None,
        semantic_cache_min_score: float = 0.78,
        semantic_cache_min_results: int = 5,
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
        self.apify_sources = apify_sources
        self.embedding = embedding or MissingEmbeddingClient()
        self.semantic_cache_min_score = semantic_cache_min_score
        self.semantic_cache_min_results = semantic_cache_min_results
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
        cached_results: list[dict[str, Any]] = []
        sources_to_run: list[CampaignSourceRead] = []
        canonical = CanonicalRepository(self.leads.session, embedding=self.embedding)
        semantic_rows: list[dict[str, Any]] = []
        over_source = bool((campaign.source_inputs or {}).get("requires_digital_opportunity"))
        website_policy = str(
            (campaign.source_inputs or {}).get("website_policy") or "any"
        )
        live_website_search = website_policy in {"missing", "missing_or_unavailable"}
        if not live_website_search:
            for source in sources:
                source_query = str(source.input.get("query") or campaign.source_input or "").strip()
                semantic_rows = canonical.list_semantic_discovery_results(
                    source_inputs=source.input,
                    source_input=source_query,
                    limit=campaign.max_leads,
                    min_score=self.semantic_cache_min_score,
                    min_results=min(self.semantic_cache_min_results, campaign.max_leads),
                )
                if semantic_rows:
                    break
        if semantic_rows:
            cached_results.extend(
                exclude_previously_delivered_rows(
                    self.leads.session,
                    campaign_id=campaign.id,
                    product_id=product.id,
                    rows=_rows_with_semantic_context(semantic_rows),
                )
            )
            if not over_source or len(cached_results) >= campaign.max_leads:
                sources = []
        else:
            for source in sources:
                if live_website_search:
                    sources_to_run.append(source)
                    continue
                limit = int(source.config.get("limit") or campaign.max_leads)
                cached_rows = canonical.list_cached_discovery_results(
                    source=source.provider_id,
                    source_input=source.input,
                    limit=limit,
                )
                if cached_rows:
                    cached_results.extend(
                        exclude_previously_delivered_rows(
                            self.leads.session,
                            campaign_id=campaign.id,
                            product_id=product.id,
                            rows=_rows_with_source_context(
                                rows=cached_rows,
                                source=source,
                                from_cache=True,
                            ),
                        )
                    )
                    if not over_source or len(cached_results) >= campaign.max_leads:
                        continue
                sources_to_run.append(source)
            sources = sources_to_run
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
                apify_sources=self.apify_sources,
                timeout_seconds=self.timeout_seconds,
            )
        )

        def decide(state: dict, iteration: int):
            if state["source_index"] >= len(sources):
                return StopAction("no more campaign discovery sources")
            if state["eligible_count"] >= campaign.max_leads:
                return StopAction("candidate target reached")
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
                enriched_rows.extend(
                    _rows_with_source_context(
                        rows=[dict(row)],
                        source=source,
                        from_cache=False,
                    )
                )
            enriched_rows = exclude_previously_delivered_rows(
                self.leads.session,
                campaign_id=campaign.id,
                product_id=product.id,
                rows=enriched_rows,
            )
            merged_rows = _merge_unique_rows(state["results"], enriched_rows)
            eligible_count = sum(
                1
                for row in merged_rows
                if assess_discovery_candidate(
                    SearchResult.model_validate(row), product
                ).is_promotable
            )
            metric = {
                "provider_id": source.provider_id,
                "stage": source.config.get("stage") or 1,
                "fetched_count": len(tool_data),
                "unique_count": len(merged_rows) - len(state["results"]),
                "eligible_count": max(0, eligible_count - state["eligible_count"]),
                "latency_ms": observation.get("latency_ms", 0)
                if isinstance(observation, dict)
                else 0,
                "cost_usd": observation.get("cost_usd", 0)
                if isinstance(observation, dict)
                else 0,
                "error": observation.get("error")
                if isinstance(observation, dict)
                else None,
            }
            return {
                "source_index": state["source_index"] + 1,
                "results": merged_rows,
                "eligible_count": eligible_count,
                "source_metrics": [*state["source_metrics"], metric],
            }

        result = runner.run(
            goal=f"Discover leads for {product.product_name}",
            initial_state={
                "source_index": 0,
                "results": cached_results,
                "eligible_count": sum(
                    1
                    for row in cached_results
                    if assess_discovery_candidate(
                        SearchResult.model_validate(row), product
                    ).is_promotable
                ),
                "source_metrics": [],
            },
            max_iterations=max(1, len(sources)),
            allowed_tools={source_tool.name},
            tools=[source_tool],
            decide=decide,
            observe=observe,
            on_tool_start=self.on_tool_start,
            on_tool_success=self.on_tool_success,
            on_tool_error=self.on_tool_error,
            continue_on_tool_error=(
                (campaign.source_inputs or {}).get("discovery_strategy") == "staged"
            ),
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
        if result.state["source_metrics"]:
            self.memory.create_observation(
                CampaignMemoryCreate(
                    product_id=product.id,
                    campaign_id=campaign.id,
                    type=ObservationType.LEAD_QUALITY,
                    content=f"Discovery source metrics: {result.state['source_metrics']}",
                    tags=["discovery", "source-metrics"],
                )
            )
        return [LeadRead.model_validate(row) for row in discovered]


def _rows_with_source_context(
    *,
    rows: list[dict[str, Any]],
    source: CampaignSourceRead,
    from_cache: bool,
) -> list[dict[str, Any]]:
    enriched_rows = []
    for row in rows:
        enriched = dict(row)
        enriched["discovery_query"] = source.input.get("query") or ""
        enriched["discovery_geography"] = source.input.get("geography") or ""
        enriched["source_input"] = source.input
        enriched["campaign_source_id"] = source.id
        enriched["provider_id"] = source.provider_id
        enriched["from_cache"] = from_cache
        enriched_rows.append(enriched)
    return enriched_rows


def _rows_with_semantic_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows = []
    for row in rows:
        enriched = dict(row)
        raw = dict(enriched.get("raw") or {})
        source_input = raw.get("source_input") if isinstance(raw.get("source_input"), dict) else {}
        enriched["discovery_query"] = raw.get("discovery_query") or raw.get("query") or ""
        enriched["discovery_geography"] = (
            raw.get("discovery_geography") or raw.get("geography") or ""
        )
        enriched["source_input"] = source_input
        enriched["campaign_source_id"] = raw.get("campaign_source_id") or ""
        enriched["provider_id"] = (
            raw.get("provider_id") or enriched.get("source") or "canonical_cache"
        )
        enriched["from_cache"] = True
        enriched["from_semantic_cache"] = True
        enriched_rows.append(enriched)
    return enriched_rows


def _merge_unique_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [dict(row) for row in existing_rows]
    key_to_index: dict[str, int] = {}
    for index, row in enumerate(merged):
        for key in _discovery_row_keys(row):
            key_to_index[key] = index

    for incoming in new_rows:
        row = dict(incoming)
        keys = _discovery_row_keys(row)
        matching_indexes = {key_to_index[key] for key in keys if key in key_to_index}
        if not matching_indexes:
            index = len(merged)
            merged.append(row)
            for key in keys:
                key_to_index[key] = index
            continue

        index = min(matching_indexes)
        current = merged[index]
        for field in ("url", "snippet", "geography", "contact_email"):
            if not current.get(field) and row.get(field):
                current[field] = row[field]
        raw = dict(current.get("raw") or {})
        evidence = list(raw.get("source_evidence") or [])
        if not evidence:
            evidence.append(
                {
                    "provider_id": current.get("provider_id") or current.get("source"),
                    "raw": current.get("raw") or {},
                }
            )
        evidence.append(
            {
                "provider_id": row.get("provider_id") or row.get("source"),
                "raw": row.get("raw") or {},
            }
        )
        raw["source_evidence"] = evidence
        current["raw"] = raw
        for key in keys:
            key_to_index[key] = index
    return merged


def _discovery_row_keys(row: dict[str, Any]) -> set[str]:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    provider = str(row.get("provider_id") or row.get("source") or "unknown")
    external_id = external_id_from_raw(raw)
    domain = normalize_domain(row.get("url"))
    phone = normalize_phone(phone_from_raw(raw))
    name = normalize_business_name(str(row.get("title") or ""))
    geography = " ".join(str(row.get("geography") or "").lower().replace(",", " ").split())
    keys: set[str] = set()
    if external_id:
        keys.add(f"external:{provider}:{external_id}")
    if domain:
        keys.add(f"domain:{domain}")
    if phone:
        keys.add(f"phone:{phone}")
    if name and geography:
        keys.add(f"name-geography:{name}|{geography}")
    if not keys and name:
        keys.add(f"name-provider:{provider}:{name}")
    return keys
