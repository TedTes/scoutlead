from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from source_providers.catalog import (
    CONFIGURED_SEARCH_PROVIDER_ID,
    GOOGLE_PLACES_PROVIDER_ID,
    OPENSTREETMAP_PROVIDER_ID,
    SOURCE_PROVIDERS,
    SOURCE_TEMPLATES,
    SourceProviderSpec,
    SourceTemplateSpec,
    niche_slug_for_category,
)


class SourceProviderRegistry:
    """Single runtime view of providers and versioned query templates.

    The registry is intentionally storage-agnostic so built-ins can later be
    replaced by database rows without changing compilers or adapters.
    """

    def __init__(
        self,
        *,
        providers: Iterable[SourceProviderSpec] | None = None,
        templates: Iterable[SourceTemplateSpec] | None = None,
        provider_configs: Iterable[dict[str, Any]] = (),
        template_configs: Iterable[dict[str, Any]] = (),
    ) -> None:
        provider_rows = list(providers or SOURCE_PROVIDERS.values())
        self._providers = {provider.id: provider for provider in provider_rows}
        self._provider_configs: dict[str, dict[str, Any]] = {
            provider.id: {} for provider in provider_rows
        }
        for config in provider_configs:
            self._merge_provider_config(config)

        template_rows = list(templates or SOURCE_TEMPLATES)
        template_rows.extend(self._template_from_config(config) for config in template_configs)
        unknown_providers = sorted(
            {template.provider_id for template in template_rows} - set(self._providers)
        )
        if unknown_providers:
            raise ValueError(
                "source templates reference unknown providers: "
                + ", ".join(unknown_providers)
            )
        self._templates = {template.id: template for template in template_rows}

    @classmethod
    def configured(
        cls,
        *,
        google_places_configured: bool,
        search_configured: bool,
        openstreetmap_enabled: bool,
        apify_sources: Iterable[dict[str, Any]] = (),
        source_templates: Iterable[dict[str, Any]] = (),
        google_places_config: dict[str, Any] | None = None,
    ) -> "SourceProviderRegistry":
        configured_apify_sources = []
        for source in apify_sources:
            source_config = dict(source)
            source_config["enabled"] = bool(
                source_config.get("enabled", True)
                and source_config.get("api_token")
                and source_config.get("actor_id")
                and (
                    source_config.get("input_template")
                    or source_config.get("search_url_template")
                    or source_config.get("input_kind")
                )
            )
            source_config.setdefault(
                "capabilities", {"configured_listing", "scraped_public_data"}
            )
            configured_apify_sources.append(source_config)
        provider_configs = [
            {
                "id": GOOGLE_PLACES_PROVIDER_ID,
                "enabled": google_places_configured,
                **(google_places_config or {}),
            },
            {"id": CONFIGURED_SEARCH_PROVIDER_ID, "enabled": search_configured},
            {"id": OPENSTREETMAP_PROVIDER_ID, "enabled": openstreetmap_enabled},
            *configured_apify_sources,
        ]
        return cls(
            provider_configs=provider_configs,
            template_configs=source_templates,
        )

    def provider(self, provider_id: str) -> SourceProviderSpec | None:
        return self._providers.get(provider_id)

    def providers(self, *, enabled_only: bool = False) -> list[SourceProviderSpec]:
        rows = list(self._providers.values())
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return sorted(rows, key=lambda row: (row.stage, row.priority, row.id))

    def config(self, provider_id: str) -> dict[str, Any]:
        return dict(self._provider_configs.get(provider_id, {}))

    def templates(
        self,
        *,
        provider_id: str | None = None,
        niche_slug: str | None = None,
        enabled_only: bool = True,
    ) -> list[SourceTemplateSpec]:
        rows = list(self._templates.values())
        if provider_id is not None:
            rows = [row for row in rows if row.provider_id == provider_id]
        if niche_slug is not None:
            rows = [row for row in rows if row.niche_slug in {niche_slug, "*"}]
        if enabled_only:
            rows = [row for row in rows if row.enabled]
        return sorted(rows, key=lambda row: (row.provider_id, row.niche_slug, row.id))

    def templates_for_category(
        self,
        provider_id: str,
        category: str,
    ) -> list[SourceTemplateSpec]:
        niche_slug = niche_slug_for_category(category)
        if niche_slug is None:
            return [
                template
                for template in self.templates(provider_id=provider_id)
                if template.niche_slug == "*"
            ]
        return self.templates(provider_id=provider_id, niche_slug=niche_slug)

    def _merge_provider_config(self, config: dict[str, Any]) -> None:
        provider_id = str(
            config.get("id")
            or config.get("provider_id")
            or config.get("source_provider_id")
            or ""
        ).strip()
        if not provider_id:
            return
        current = self._providers.get(provider_id)
        if current is None:
            current = SourceProviderSpec(
                id=provider_id,
                label=str(config.get("label") or provider_id),
                adapter_kind=str(config.get("adapter_kind") or "apify_actor"),
                capabilities=frozenset(config.get("capabilities") or {"configured_source"}),
                version=int(config.get("version") or 1),
                enabled=bool(config.get("enabled", True)),
                stage=int(config.get("stage") or 3),
                priority=int(config.get("priority") or 30),
                cost=str(config.get("cost") or "metered"),
                detail=str(config.get("detail") or ""),
            )
        else:
            current = replace(
                current,
                label=str(config.get("label") or current.label),
                enabled=bool(config.get("enabled", current.enabled)),
                version=int(config.get("version") or current.version),
                stage=int(config.get("stage") or current.stage),
                priority=int(config.get("priority") or current.priority),
                cost=str(config.get("cost") or current.cost),
                detail=str(config.get("detail") or current.detail),
            )
        self._providers[provider_id] = current
        self._provider_configs[provider_id] = dict(config)

    @staticmethod
    def _template_from_config(config: dict[str, Any]) -> SourceTemplateSpec:
        template_id = str(config.get("id") or "").strip()
        provider_id = str(config.get("provider_id") or "configured_search").strip()
        template = str(config.get("query_template") or config.get("template") or "").strip()
        if not template_id or not template:
            raise ValueError("source template config requires id and template")
        metadata = {
            key: value
            for key, value in config.items()
            if key
            not in {
                "id",
                "provider_id",
                "niche_slug",
                "query_template",
                "template",
                "version",
                "enabled",
                "purpose",
            }
        }
        return SourceTemplateSpec(
            id=template_id,
            provider_id=provider_id,
            niche_slug=str(config.get("niche_slug") or "*"),
            template=template,
            version=int(config.get("version") or 1),
            enabled=bool(config.get("enabled", True)),
            purpose=str(config.get("purpose") or "discovery"),
            metadata=metadata,
        )
