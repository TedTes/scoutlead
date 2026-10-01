from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from canonical.semantics import market_is_compatible, semantic_key
from db.models import (
    BusinessIndexSegmentModel,
    BusinessNicheMembershipModel,
    NicheModel,
)
from niches.resolver import resolve_niche
from shared.utils import new_id, normalize_text, utcnow


class BusinessIndexRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_or_create_segment(
        self,
        *,
        product_id: str,
        business_category: str,
        market_label: str,
        source_plan: list[dict],
        target_business_count: int,
    ) -> BusinessIndexSegmentModel:
        source_inputs = {
            "business_category": business_category,
            "location": market_label,
            "source_request_intent": {
                "business_category": business_category,
                "location": market_label,
            },
        }
        resolution = resolve_niche(
            self.session,
            source_inputs=source_inputs,
            source_input=f"{business_category} in {market_label}",
        )
        if resolution is None:
            niche = self._create_niche(business_category, market_label)
            niche_id = niche.id
        else:
            niche_id = resolution.niche_id
        market_key = semantic_key(market_label) or "unknown"
        segment = self.session.scalar(
            select(BusinessIndexSegmentModel)
            .where(
                BusinessIndexSegmentModel.niche_id == niche_id,
                BusinessIndexSegmentModel.market_key == market_key,
            )
            .limit(1)
        )
        now = utcnow()
        if segment is None:
            segment = BusinessIndexSegmentModel(
                id=new_id("index_segment"),
                niche_id=niche_id,
                product_id=product_id,
                market_key=market_key,
                market_label=normalize_text(market_label) or market_key,
                status="active",
                demand_count=1,
                target_business_count=target_business_count,
                source_plan=source_plan,
                source_state={},
                next_refresh_at=now,
            )
            self.session.add(segment)
        else:
            segment.product_id = product_id
            segment.market_label = normalize_text(market_label) or segment.market_label
            segment.status = "active"
            segment.demand_count += 1
            segment.target_business_count = max(
                segment.target_business_count,
                target_business_count,
            )
            segment.source_plan = source_plan or segment.source_plan
            segment.next_refresh_at = segment.next_refresh_at or now
        self.session.commit()
        self.session.refresh(segment)
        return segment

    def get(self, segment_id: str) -> BusinessIndexSegmentModel | None:
        return self.session.get(BusinessIndexSegmentModel, segment_id)

    def business_ids(self, segment: BusinessIndexSegmentModel) -> list[str]:
        memberships = self.session.scalars(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.niche_id == segment.niche_id
            )
        )
        return list(
            dict.fromkeys(
                membership.business_id
                for membership in memberships
                if market_is_compatible(segment.market_key, membership.market_key)
            )
        )

    def due(self, *, limit: int = 25) -> list[BusinessIndexSegmentModel]:
        now = utcnow()
        candidates = list(
            self.session.scalars(
                select(BusinessIndexSegmentModel)
                .where(
                    BusinessIndexSegmentModel.status == "active",
                    BusinessIndexSegmentModel.next_refresh_at.is_not(None),
                    BusinessIndexSegmentModel.next_refresh_at <= now,
                )
                .limit(max(limit * 8, 100))
            )
        )
        coverage = {
            (niche_id, market_key): count
            for niche_id, market_key, count in self.session.execute(
                select(
                    BusinessNicheMembershipModel.niche_id,
                    BusinessNicheMembershipModel.market_key,
                    func.count(BusinessNicheMembershipModel.id),
                ).group_by(
                    BusinessNicheMembershipModel.niche_id,
                    BusinessNicheMembershipModel.market_key,
                )
            )
        }
        candidates.sort(
            key=lambda segment: _refresh_priority(
                segment,
                available_count=coverage.get((segment.niche_id, segment.market_key), 0),
                now=now,
            ),
            reverse=True,
        )
        return candidates[:limit]

    def record_source_result(
        self,
        segment: BusinessIndexSegmentModel,
        *,
        provider_id: str,
        state: dict,
    ) -> None:
        segment.source_state = {**(segment.source_state or {}), provider_id: state}
        segment.last_refresh_at = utcnow()
        self.session.commit()

    def complete_refresh(self, segment: BusinessIndexSegmentModel, *, succeeded: bool) -> None:
        now = utcnow()
        segment.last_refresh_at = now
        if succeeded:
            segment.last_success_at = now
        segment.next_refresh_at = now + timedelta(days=7 if succeeded else 1)
        self.session.commit()

    def _create_niche(self, business_category: str, market_label: str) -> NicheModel:
        category = normalize_text(business_category) or "local businesses"
        base_slug = (semantic_key(category) or "local_businesses").replace(" ", "_")[:220]
        slug = base_slug
        suffix = 1
        while self.session.scalar(select(NicheModel.id).where(NicheModel.slug == slug)):
            suffix += 1
            slug = f"{base_slug[: 220 - len(str(suffix))]}_{suffix}"
        niche = NicheModel(
            id=new_id("niche"),
            slug=slug,
            label=" ".join(word.capitalize() for word in category.split()),
            category=category,
            default_query=f"{category} in {normalize_text(market_label)}",
            active=True,
            signal_vocabulary=[],
        )
        self.session.add(niche)
        self.session.flush()
        return niche


def _refresh_priority(
    segment: BusinessIndexSegmentModel,
    *,
    available_count: int,
    now: datetime,
) -> tuple[int, int, float, int]:
    successful_sources = sum(
        1
        for state in (segment.source_state or {}).values()
        if isinstance(state, dict) and state.get("last_success_at")
    )
    source_diversity_gap = max(0, len(segment.source_plan or []) - successful_sources)
    coverage_gap = max(0, segment.target_business_count - available_count)
    reference = segment.last_success_at or segment.created_at
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    evidence_age_seconds = max(0.0, (now - reference).total_seconds())
    return (
        segment.demand_count,
        coverage_gap,
        evidence_age_seconds,
        source_diversity_gap,
    )
