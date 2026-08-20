from __future__ import annotations

from typing import Any, Protocol

from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignRead
from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead
from shared.errors import ConfigurationError
from tools.base import ToolResult, ToolSlot, measured_tool_result
from tools.search import SearchTool


class SourceAdapter(Protocol):
    provider_id: str

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


class ConfiguredSearchAdapter:
    provider_id = "configured_search"

    def __init__(self, search_tool: SearchTool) -> None:
        self.search_tool = search_tool

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        product = ProductRead.model_validate(context["product"])
        campaign = CampaignRead.model_validate(context["campaign"])
        query = str(source.input.get("query") or "").strip()
        if not query:
            raise ConfigurationError(
                "campaign source query is empty",
                {"campaign_source_id": source.id, "provider_id": source.provider_id},
            )
        source_type = DiscoverySourceType(source.input.get("source_type") or DiscoverySourceType.WEB_SEARCH)
        limit = int(source.config.get("limit") or campaign.max_leads)
        discovery_source = DiscoverySource(type=source_type, value=query, limit=limit)

        def action() -> list[dict[str, Any]]:
            return [
                result.model_dump(mode="json")
                for result in self.search_tool.search(
                    product=product,
                    campaign=campaign,
                    source=discovery_source,
                    limit=limit,
                    query=query,
                )
            ]

        return measured_tool_result(
            provider=self.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=80 if self.search_tool.is_configured or source_type == DiscoverySourceType.SEED else 0,
            raw={
                "campaign_source_id": source.id,
                "provider_id": source.provider_id,
                "input": source.input,
                "config": source.config,
            },
            action=action,
        )


class SeedAdapter:
    provider_id = "seed"

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        product = ProductRead.model_validate(context["product"])
        query = str(source.input.get("query") or source.input.get("value") or "").strip()
        if not query:
            raise ConfigurationError(
                "seed source is empty",
                {"campaign_source_id": source.id, "provider_id": source.provider_id},
            )

        def action() -> list[dict[str, Any]]:
            parsed = SearchTool._parse_seed(query, product.target_geography)
            return [parsed.model_dump(mode="json")]

        return measured_tool_result(
            provider=self.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=90,
            raw={"campaign_source_id": source.id, "input": source.input},
            action=action,
        )
