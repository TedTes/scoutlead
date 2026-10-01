from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from source_requests.schemas import (
    CONFIGURED_SEARCH_PROVIDER_ID,
    GOOGLE_PLACES_PROVIDER_ID,
    OPENSTREETMAP_PROVIDER_ID,
)


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
    catalog = [
        SourceCapability(
            id=GOOGLE_PLACES_PROVIDER_ID,
            label="Google Places",
            configured=google_places_configured,
            capabilities=("local_business", "phone", "ratings", "website_listing"),
            stage=1,
            cost="metered",
            detail="Primary structured local-business discovery",
        ),
        SourceCapability(
            id=OPENSTREETMAP_PROVIDER_ID,
            label="OpenStreetMap",
            configured=openstreetmap_enabled,
            capabilities=("local_business", "address", "phone", "website_listing"),
            stage=2,
            cost="free",
            detail="Secondary open-data coverage",
        ),
        SourceCapability(
            id=CONFIGURED_SEARCH_PROVIDER_ID,
            label="Web search",
            configured=search_configured,
            capabilities=("public_web", "official_website", "directory_reference"),
            stage=2,
            cost="metered",
            detail="Public-web discovery and website confirmation",
        ),
    ]
    for source in apify_sources or []:
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            continue
        configured = bool(
            source.get("api_token")
            and source.get("actor_id")
            and (
                source.get("input_template")
                or source.get("search_url_template")
                or source.get("input_kind")
            )
        )
        catalog.append(
            SourceCapability(
                id=source_id,
                label=str(source.get("label") or source_id),
                configured=configured,
                capabilities=("configured_listing", "scraped_public_data"),
                stage=3,
                cost="metered",
                detail=str(source.get("detail") or "Configured listing source"),
            )
        )
    return catalog
