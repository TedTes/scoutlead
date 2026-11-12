from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from business_index.repository import BusinessIndexRepository
from canonical.semantics import semantic_key
from db.models import TerritoryModel
from job_queue.service import QueueService
from products.repository import ProductRepository
from products.schemas import ProductRead
from source_requests.compiler import SourceRequestCompiler
from source_requests.schemas import SourceRequestCreate, SourceRequestIntent
from source_providers.registry import SourceProviderRegistry


def enqueue_profile_source_expansion(
    session: Session,
    profile: TerritoryModel,
    *,
    google_places_configured: bool,
    search_configured: bool,
    openstreetmap_enabled: bool,
    apify_sources: list[dict[str, Any]],
    source_recipes: list[dict[str, Any]],
    market_keys: set[str] | None = None,
    enqueue_refresh: bool = True,
) -> list[str]:
    """Ensure independently refreshable segments, optionally starting collection."""

    product = ProductRead.model_validate(
        ProductRepository(
            session,
            workspace_id=profile.workspace_id,
        ).get(profile.product_id)
    )
    segments = BusinessIndexRepository(session)
    queue = QueueService(session)
    compiler = SourceRequestCompiler(
        SourceProviderRegistry.configured(
            google_places_configured=google_places_configured,
            search_configured=search_configured,
            openstreetmap_enabled=openstreetmap_enabled,
            apify_sources=apify_sources,
            source_templates=source_recipes,
        )
    )
    target_business_count = min(100, max(profile.batch_size * 4, profile.batch_size))
    niche = profile.niche
    if niche is None or not niche.active:
        return []
    config = niche.search_config or {}
    business_category = str(config.get("provider_category") or niche.category or niche.label)
    query_template = str(config.get("query_template") or "{category} in {city}")
    market_labels = list(
        dict.fromkeys(
            str(location.get("label") or location.get("city") or "")
            for location in (profile.locations or [])
            if str(location.get("label") or location.get("city") or "").strip()
        )
    ) or [profile.city]
    if market_keys is not None:
        market_labels = [
            market_label
            for market_label in market_labels
            if semantic_key(market_label) in market_keys
        ]
    segment_ids: list[str] = []
    for market_label in market_labels:
        search_query = query_template.format(category=business_category, city=market_label)
        intent = SourceRequestIntent(
            business_category=business_category,
            location=market_label,
            search_query=search_query,
            confidence=100,
            rationale="Derived from the saved multi-city search.",
        )
        plan = compiler.compile_auto(
            request=SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt=intent.search_query,
                business_category=intent.business_category,
                geography=intent.location,
                max_results=target_business_count,
                run_immediately=False,
            ),
            product=product,
            intent=intent,
            website_policy="any",
        )
        if not plan.tasks:
            continue
        segment = segments.resolve_or_create_segment(
            niche_id=niche.id,
            business_category=business_category,
            market_label=market_label,
            source_plan=[task.model_dump(mode="json") for task in plan.tasks],
            target_business_count=target_business_count,
            record_demand=False,
        )
        if enqueue_refresh:
            available_count = len(segments.business_ids(segment))
            queue.enqueue_business_index_refresh(
                segment_id=segment.id,
                requested_deficit=max(0, target_business_count - available_count),
                commit=False,
            )
        segment_ids.append(segment.id)

    session.commit()
    return segment_ids
