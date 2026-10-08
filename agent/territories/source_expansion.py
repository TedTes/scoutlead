from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_index.repository import BusinessIndexRepository
from db.models import NicheModel, TerritoryModel
from job_queue.service import QueueService
from products.repository import ProductRepository
from products.schemas import ProductRead
from source_requests.compiler import SourceRequestCompiler
from source_requests.schemas import SourceRequestCreate, SourceRequestIntent
from territories.profile_catalog import profile_trade_spec


def enqueue_profile_source_expansion(
    session: Session,
    profile: TerritoryModel,
    *,
    google_places_configured: bool,
    search_configured: bool,
    openstreetmap_enabled: bool,
    apify_sources: list[dict[str, Any]],
    source_recipes: list[dict[str, Any]],
) -> list[str]:
    """Ensure each profile trade has an independently refreshable source segment."""
    if not profile.trade_keys:
        return []

    product = ProductRead.model_validate(
        ProductRepository(
            session,
            workspace_id=profile.workspace_id,
        ).get(profile.product_id)
    )
    segments = BusinessIndexRepository(session)
    queue = QueueService(session)
    compiler = SourceRequestCompiler()
    target_business_count = min(100, max(profile.batch_size * 4, profile.batch_size))
    queued_segment_ids: list[str] = []

    for trade_key in profile.trade_keys:
        spec = profile_trade_spec(trade_key)
        niche = session.scalar(
            select(NicheModel).where(NicheModel.slug == spec.niche_slug).limit(1)
        )
        if niche is None or not niche.active:
            continue
        intent = SourceRequestIntent(
            business_category=spec.niche_category,
            location=profile.city,
            search_query=f"{spec.niche_category} in {profile.city}",
            confidence=100,
            rationale="Derived from the saved audience profile.",
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
            google_places_configured=google_places_configured,
            search_configured=search_configured,
            openstreetmap_enabled=openstreetmap_enabled,
            apify_sources=apify_sources,
            source_recipes=source_recipes,
            intent=intent,
            website_policy="any",
        )
        segment = segments.resolve_or_create_segment(
            product_id=product.id,
            niche_id=niche.id,
            business_category=spec.niche_category,
            market_label=profile.city,
            source_plan=[task.model_dump(mode="json") for task in plan.tasks],
            target_business_count=target_business_count,
            record_demand=False,
        )
        available_count = len(segments.business_ids(segment))
        queue.enqueue_business_index_refresh(
            segment_id=segment.id,
            requested_deficit=max(0, target_business_count - available_count),
            commit=False,
        )
        queued_segment_ids.append(segment.id)

    session.commit()
    return queued_segment_ids
