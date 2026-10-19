from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from source_providers.registry import SourceProviderRegistry


@dataclass(frozen=True)
class SourceCapability:
    id: str
    label: str
    configured: bool
    capabilities: tuple[str, ...]
    stage: int
    cost: str
    detail: str


def build_source_catalog(
    *,
    google_places_configured: bool,
    search_configured: bool,
    openstreetmap_enabled: bool = True,
    apify_sources: list[dict[str, Any]] | None = None,
) -> list[SourceCapability]:
    registry = SourceProviderRegistry.configured(
        google_places_configured=google_places_configured,
        search_configured=search_configured,
        openstreetmap_enabled=openstreetmap_enabled,
        apify_sources=apify_sources or [],
    )
    return [
        SourceCapability(
            id=provider.id,
            label=provider.label,
            configured=provider.enabled,
            capabilities=tuple(sorted(provider.capabilities)),
            stage=provider.stage,
            cost=provider.cost,
            detail=provider.detail,
        )
        for provider in registry.providers()
        if provider.adapter_kind != "seed"
    ]
