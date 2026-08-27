from __future__ import annotations

from typing import Any

from campaign_sources.schemas import CampaignSourceRead
from shared.errors import ConfigurationError
from tools.base import ToolResult
from tools.discovery.apify_actor import ApifyActorDiscoveryAdapter
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
        apify_api_token: str | None = None,
        apify_api_base_url: str | None = None,
        apify_source_provider_id: str = "apify_actor",
        apify_actor_id: str | None = None,
        apify_actor_input_template: str | None = None,
        apify_actor_result_mapping: str | None = None,
        apify_actor_max_charge_usd: float | None = None,
        apify_sources: list[dict[str, Any]] | None = None,
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
        apify_source_configs = apify_sources
        if apify_source_configs is None:
            apify_source_configs = [
                {
                    "id": apify_source_provider_id,
                    "actor_id": apify_actor_id,
                    "api_token": apify_api_token,
                    "api_base_url": apify_api_base_url,
                    "input_template": apify_actor_input_template,
                    "result_mapping": apify_actor_result_mapping,
                    "max_charge_usd": apify_actor_max_charge_usd,
                }
            ]
        for source_config in apify_source_configs:
            provider_id = str(
                source_config.get("id")
                or source_config.get("provider_id")
                or source_config.get("source_provider_id")
                or ""
            ).strip()
            if not provider_id:
                continue
            adapters.append(
                ApifyActorDiscoveryAdapter(
                    provider_id=provider_id,
                    api_token=source_config.get("api_token") or apify_api_token,
                    api_base_url=source_config.get("api_base_url") or apify_api_base_url,
                    actor_id=source_config.get("actor_id"),
                    input_template=source_config.get("input_template"),
                    result_mapping=source_config.get("result_mapping"),
                    max_charge_usd=source_config.get("max_charge_usd"),
                    timeout_seconds=timeout_seconds,
                )
            )
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
