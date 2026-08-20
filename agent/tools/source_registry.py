from __future__ import annotations

from typing import Any

from campaign_sources.schemas import CampaignSourceRead
from shared.errors import ConfigurationError
from tools.base import ToolResult
from tools.discovery.google_places import GooglePlacesDiscoveryAdapter
from tools.search import SearchTool
from tools.source_adapters import ConfiguredSearchAdapter, SeedAdapter, SourceAdapter


class SourceAdapterRegistry:
    def __init__(
        self,
        *,
        search_tool: SearchTool,
        google_places_api_key: str | None = None,
        google_places_api_endpoint: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        adapters: list[SourceAdapter] = [
            ConfiguredSearchAdapter(search_tool),
            GooglePlacesDiscoveryAdapter(
                api_key=google_places_api_key,
                endpoint=google_places_api_endpoint,
                timeout_seconds=timeout_seconds,
            ),
            SeedAdapter(),
        ]
        self.adapters = {adapter.provider_id: adapter for adapter in adapters}

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        adapter = self.adapters.get(source.provider_id)
        if adapter is None:
            raise ConfigurationError(
                "campaign source provider is not registered",
                {"provider_id": source.provider_id, "campaign_source_id": source.id},
            )
        return adapter.run(source, context)

    def missing_configuration(self, provider_ids: list[str]) -> list[str]:
        missing = []
        for provider_id in provider_ids:
            adapter = self.adapters.get(provider_id)
            if adapter is None:
                continue
            if not bool(getattr(adapter, "is_configured", True)):
                missing.append(provider_id)
        return missing


class CampaignSourceTool:
    name = "campaign_source"

    def __init__(self, registry: SourceAdapterRegistry) -> None:
        self.registry = registry

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        source = CampaignSourceRead.model_validate(args["source"])
        result = self.registry.run(source, args["context"])
        return result.model_dump()
