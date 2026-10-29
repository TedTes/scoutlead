from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_validation.validation import is_generic_business_title
from canonical.website_evidence import BLOCKED_WEBSITE_HOSTS
from db.models import (
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    SourceObservationModel,
)
from source_observations.families import source_family


@dataclass
class InventoryCleanupSummary:
    dry_run: bool
    evaluated: int = 0
    archived: int = 0
    quarantined: int = 0
    retained: int = 0
    details: list[dict[str, object]] = field(default_factory=list)


def cleanup_search_origin_inventory(
    session: Session,
    *,
    apply: bool = False,
    limit: int = 5000,
) -> InventoryCleanupSummary:
    """Classify businesses whose only origin is unstructured web search.

    Dry-run is the default. Obvious result pages are archived; plausible entity
    names are quarantined for structured-provider verification. User review
    history is deliberately preserved.
    """

    businesses = list(
        session.scalars(
            select(BusinessModel)
            .where(BusinessModel.status.in_(("active", "quarantined")))
            .order_by(BusinessModel.id)
            .limit(limit)
        )
    )
    business_ids = [business.id for business in businesses]
    observations = list(
        session.scalars(
            select(SourceObservationModel).where(
                SourceObservationModel.business_id.in_(business_ids)
            )
        )
    )
    sources_by_business: dict[str, set[str]] = {}
    hosts_by_business: dict[str, set[str]] = {}
    for observation in observations:
        sources_by_business.setdefault(observation.business_id, set()).add(
            observation.source
        )
        if observation.source_url:
            host = observation.source_url.split("//", 1)[-1].split("/", 1)[0]
            hosts_by_business.setdefault(observation.business_id, set()).add(
                host.lower().removeprefix("www.")
            )

    summary = InventoryCleanupSummary(dry_run=not apply)
    for business in businesses:
        sources = sources_by_business.get(business.id, set())
        if "configured_search" not in sources:
            continue
        summary.evaluated += 1
        independent_sources = {
            source
            for source in sources
            if source_family(source) == "independent_discovery"
        }
        if independent_sources:
            summary.retained += 1
            continue
        hosts = hosts_by_business.get(business.id, set())
        blocked_host = any(
            host == blocked or host.endswith(f".{blocked}")
            for host in hosts
            for blocked in BLOCKED_WEBSITE_HOSTS
        )
        obvious_result_page = (
            is_generic_business_title(business.display_name)
            or business.is_directory is True
            or blocked_host
        )
        target_status = "archived" if obvious_result_page else "quarantined"
        if target_status == "archived":
            summary.archived += 1
        else:
            summary.quarantined += 1
        summary.details.append(
            {
                "business_id": business.id,
                "name": business.display_name,
                "current_status": business.status,
                "target_status": target_status,
                "sources": sorted(sources),
                "reason": (
                    "obvious search-result or directory record"
                    if obvious_result_page
                    else "no independent structured discovery source"
                ),
            }
        )
        if not apply:
            continue
        business.status = target_status
        for membership in session.scalars(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.business_id == business.id
            )
        ):
            membership.confidence = 0.0
        for fact in session.scalars(
            select(BusinessFactModel).where(
                BusinessFactModel.business_id == business.id
            )
        ):
            fact.quality_state = "rejected"
            fact.resolution_state = "invalid_source"
            fact.confidence = 0

    if apply:
        session.commit()
    return summary
