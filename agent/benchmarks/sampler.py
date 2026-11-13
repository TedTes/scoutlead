from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from benchmarks.schemas import BenchmarkObserved, BenchmarkRecord
from business_attributes.eligibility import fact_is_eligible
from business_attributes.repository import BusinessAttributeRepository, attribute_value
from db.models import (
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    BusinessAttributeModel,
)
from seeding.batches import active_membership_condition
from shared.utils import utcnow


def sample_businesses(
    session: Session,
    *,
    niche_slugs: list[str],
    per_niche: int = 50,
    market_key: str | None = None,
) -> list[BenchmarkRecord]:
    selected: list[tuple[BusinessModel, str]] = []
    seen: set[str] = set()
    for slug in niche_slugs:
        statement = (
            select(BusinessModel)
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .where(NicheModel.slug == slug, active_membership_condition())
        )
        if market_key:
            statement = statement.where(
                BusinessNicheMembershipModel.market_key == market_key
            )
        statement = statement.order_by(func.md5(BusinessModel.id)).limit(per_niche * 2)
        count = 0
        for business in session.scalars(statement):
            if business.id in seen:
                continue
            seen.add(business.id)
            selected.append((business, slug))
            count += 1
            if count >= per_niche:
                break

    ids = [business.id for business, _ in selected]
    stored_facts = BusinessAttributeRepository(session).map_for_businesses(ids)
    now = utcnow()
    facts = {
        business_id: {
            key: fact
            for key, fact in business_attributes.items()
            if fact_is_eligible(
                fact,
                minimum_confidence=90,
                now=now,
                require_provenance=True,
            )
        }
        for business_id, business_attributes in stored_facts.items()
    }
    memberships: dict[str, list[str]] = defaultdict(list)
    source_urls: dict[str, list[str]] = defaultdict(list)
    if ids:
        for business_id, slug in session.execute(
            select(BusinessNicheMembershipModel.business_id, NicheModel.slug)
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .where(
                BusinessNicheMembershipModel.business_id.in_(ids),
                active_membership_condition(),
            )
        ):
            memberships[str(business_id)].append(str(slug))
        for observation in session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id.in_(ids),
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        ):
            if observation.source_url and observation.source_url not in source_urls[observation.business_id]:
                source_urls[observation.business_id].append(observation.source_url)

    return [
        _record(
            business,
            sampled_niche=sampled_slug,
            market_key=market_key,
            trade_keys=memberships[business.id] or [sampled_slug],
            facts=facts.get(business.id, {}),
            source_urls=source_urls[business.id][:5],
        )
        for business, sampled_slug in selected
    ]


def _record(
    business: BusinessModel,
    *,
    sampled_niche: str,
    market_key: str | None,
    trade_keys: list[str],
    facts: dict,
    source_urls: list[str],
) -> BenchmarkRecord:
    def value(key: str):
        return attribute_value(facts.get(key))

    review_count = value("google_review_count")
    return BenchmarkRecord(
        business_id=business.id,
        sampled_niche=sampled_niche,
        market_key=market_key or business.market_key,
        display_name=business.display_name,
        address=business.address,
        city=business.geography,
        phone=business.phone,
        website_url=business.website_url,
        source_urls=source_urls,
        observed=BenchmarkObserved(
            trade_keys=sorted(set(trade_keys)),
            customer_kind=business.customer_kind,
            operational=value("business_operational"),
            website_status=value("website_status"),
            mobile_viewport_present=value("mobile_viewport_present"),
            primary_cta_present=value("primary_cta_present"),
            click_to_call_present=value("click_to_call_present"),
            online_payment_or_financing_present=value(
                "online_payment_or_financing_present"
            ),
            service_area_pages_present=value("service_area_pages_present"),
            review_count=int(review_count) if review_count is not None else None,
            is_chain=business.is_chain,
            is_franchise=business.is_franchise,
            is_directory=business.is_directory,
            is_agency=business.is_agency,
        ),
    )
