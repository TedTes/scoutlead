from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from canonical.normalization import normalize_domain, normalize_phone
from db.models import (
    BusinessAttributeModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
)
from shared.geospatial import haversine_distance_km
from shared.utils import utcnow
from business_evidence.integrity import evaluate_evidence_integrity


@dataclass(frozen=True)
class MarketScope:
    label: str
    latitude: float
    longitude: float
    radius_km: float = 25.0


@dataclass(frozen=True)
class ProviderBudget:
    provider_id: str
    max_requests: int


def export_city_category(
    session: Session,
    *,
    market: MarketScope,
    niche_slug: str,
    target_count: int,
    candidate_limit: int,
    provider_budgets: Iterable[ProviderBudget] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a non-mutating readiness export from canonical persisted data."""

    checked_at = now or utcnow()
    niche = session.scalar(
        select(NicheModel).where(NicheModel.slug == niche_slug).limit(1)
    )
    if niche is None:
        raise ValueError(f"unknown niche: {niche_slug}")

    membership_rows = list(
        session.execute(
            select(BusinessModel, BusinessNicheMembershipModel)
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .where(BusinessNicheMembershipModel.niche_id == niche.id)
            .order_by(
                BusinessNicheMembershipModel.confidence.desc(),
                BusinessModel.display_name,
                BusinessModel.id,
            )
        )
    )
    scoped: list[tuple[BusinessModel, BusinessNicheMembershipModel, float]] = []
    excluded_missing_coordinates = 0
    excluded_outside_radius = 0
    for business, membership in membership_rows:
        if business.latitude is None or business.longitude is None:
            excluded_missing_coordinates += 1
            continue
        distance = haversine_distance_km(
            market.latitude,
            market.longitude,
            float(business.latitude),
            float(business.longitude),
        )
        if distance > market.radius_km:
            excluded_outside_radius += 1
            continue
        scoped.append((business, membership, round(distance, 3)))
    within_radius_before_limit = len(scoped)
    scoped = scoped[: max(1, candidate_limit)]

    business_ids = [business.id for business, _, _ in scoped]
    observations = _group_by_business(
        session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id.in_(business_ids),
                BusinessAttributeModel.row_type == "evidence",
            )
            .order_by(BusinessAttributeModel.observed_at.desc())
        )
        if business_ids
        else []
    )
    facts = _group_by_business(
        session.scalars(
            select(BusinessAttributeModel)
            .where(
                BusinessAttributeModel.business_id.in_(business_ids),
                BusinessAttributeModel.row_type == "attribute",
            )
            .order_by(BusinessAttributeModel.attribute_key)
        )
        if business_ids
        else []
    )
    contacts = _group_by_business(
        session.scalars(
            select(ContactModel)
            .where(ContactModel.business_id.in_(business_ids))
            .order_by(ContactModel.created_at.desc())
        )
        if business_ids
        else []
    )

    buckets: dict[str, list[dict[str, Any]]] = {
        "validated": [],
        "uncertain": [],
        "rejected": [],
    }
    source_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    for business, membership, distance_km in scoped:
        state, reasons = _quality_state(business)
        business_observations = observations.get(business.id, [])
        source_counts.update(row.source for row in business_observations)
        integrity = _observation_summary(business_observations, now=checked_at)
        issue_counts.update(integrity["issue_counts"])
        buckets[state].append(
            _business_record(
                business,
                membership=membership,
                distance_km=distance_km,
                quality_state=state,
                quality_reasons=reasons,
                observations=business_observations,
                observation_summary=integrity,
                facts=facts.get(business.id, []),
                contacts=contacts.get(business.id, []),
                now=checked_at,
            )
        )

    for rows in buckets.values():
        rows.sort(key=lambda row: (row["distance_km"], row["name"].casefold(), row["id"]))

    validated_count = len(buckets["validated"])
    validated_ids = {record["id"] for record in buckets["validated"]}
    request_budgets = {
        budget.provider_id: max(0, int(budget.max_requests))
        for budget in provider_budgets
    }
    return {
        "manifest": {
            "generated_at": checked_at.isoformat(),
            "database_mutated": False,
            "external_requests_executed": 0,
            "market": {
                "label": market.label,
                "latitude": market.latitude,
                "longitude": market.longitude,
                "radius_km": market.radius_km,
            },
            "niche": {
                "id": niche.id,
                "slug": niche.slug,
                "label": niche.label,
                "category": niche.category,
            },
            "target_count": target_count,
            "candidate_limit": candidate_limit,
            "counts": {
                "memberships_considered": len(membership_rows),
                "within_radius": len(scoped),
                "within_radius_before_limit": within_radius_before_limit,
                "candidate_limit_reached": within_radius_before_limit > len(scoped),
                "validated": validated_count,
                "uncertain": len(buckets["uncertain"]),
                "rejected": len(buckets["rejected"]),
                "coverage_deficit": max(0, target_count - validated_count),
                "excluded_missing_coordinates": excluded_missing_coordinates,
                "excluded_outside_radius": excluded_outside_radius,
            },
            "source_counts": dict(sorted(source_counts.items())),
            "observation_issue_counts": dict(sorted(issue_counts.items())),
            "duplicate_candidates": {
                **_duplicate_summary(scoped),
                "validated_only": _duplicate_summary(
                    [
                        row
                        for row in scoped
                        if row[0].id in validated_ids
                    ]
                ),
            },
            "collection_plan": {
                "mode": "dry_run",
                "allowed_provider_request_budgets": request_budgets,
                "hard_request_cap": sum(request_budgets.values()),
                "requested_deficit": max(0, target_count - validated_count),
                "note": (
                    "This export never calls providers. Budgets must be supplied to a "
                    "separate reviewed collection run before external requests are allowed."
                ),
            },
            "quality_gate": {
                "model": "canonical_business_attributes",
                "confirmed_attributes_are_searchable": True,
                "separate_validation_rows_required": False,
            },
        },
        **buckets,
    }


def _group_by_business(rows: Iterable[Any]) -> dict[str, list[Any]]:
    grouped: defaultdict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[str(row.business_id)].append(row)
    return grouped


def _quality_state(
    business: BusinessModel,
) -> tuple[str, list[str]]:
    if business.status != "active":
        return "rejected", [f"Business status is {business.status}."]
    if business.is_directory is True:
        return "rejected", ["Record represents a directory rather than a business."]
    return "validated", ["Active canonical business record."]


def _business_record(
    business: BusinessModel,
    *,
    membership: BusinessNicheMembershipModel,
    distance_km: float,
    quality_state: str,
    quality_reasons: list[str],
    observations: list[BusinessAttributeModel],
    observation_summary: dict[str, Any],
    facts: list[BusinessAttributeModel],
    contacts: list[ContactModel],
    now: datetime,
) -> dict[str, Any]:
    eligible_facts = []
    for fact in facts:
        eligible = bool(
            fact.resolution_state == "confirmed"
            and fact.confidence >= 90
            and (fact.expires_at is None or _aware(fact.expires_at) > _aware(now))
            and bool(fact.source or fact.source_url or fact.supporting_evidence_ids)
        )
        eligible_facts.append(
            {
                "key": fact.attribute_key,
                "value": _attribute_value(fact),
                "confidence": fact.confidence,
                "resolution_state": fact.resolution_state,
                "observed_at": fact.observed_at.isoformat(),
                "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
                "supporting_evidence_ids": fact.supporting_evidence_ids,
                "eligible": eligible,
            }
        )
    return {
        "id": business.id,
        "name": business.display_name,
        "status": business.status,
        "website_url": business.website_url,
        "domain": business.domain,
        "phone": business.phone,
        "address": business.address,
        "geography": business.geography,
        "latitude": business.latitude,
        "longitude": business.longitude,
        "distance_km": distance_km,
        "membership": {
            "id": membership.id,
            "market_key": membership.market_key,
            "confidence": membership.confidence,
        },
        "quality": {
            "state": quality_state,
            "reasons": quality_reasons,
            "attribute_model": "canonical",
        },
        "facts": eligible_facts,
        "contacts": [
            {
                "email": row.email,
                "phone": row.phone,
                "verification_status": row.verification_status,
                "verification_provider": row.verification_provider,
            }
            for row in contacts
        ],
        "observations": {
            **observation_summary,
            "references": [
                {
                    "id": row.id,
                    "source": row.source,
                    "external_id": row.external_id,
                    "source_url": row.source_url,
                    "observed_at": row.observed_at.isoformat(),
                }
                for row in observations
            ],
        },
    }


def _observation_summary(
    observations: list[BusinessAttributeModel],
    *,
    now: datetime,
) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    for observation in observations:
        result = evaluate_evidence_integrity(observation, now=now, require_locator=True)
        status_counts[result.status] += 1
        issue_counts.update(
            f"{check.status}:{check.name}"
            for check in result.checks
            if check.status in {"failed", "uncertain"}
        )
    return {
        "count": len(observations),
        "source_count": len({row.source for row in observations}),
        "sources": dict(sorted(Counter(row.source for row in observations).items())),
        "status_counts": dict(sorted(status_counts.items())),
        "issue_counts": dict(sorted(issue_counts.items())),
        "latest_observed_at": (
            max((_aware(row.observed_at) for row in observations)).isoformat()
            if observations
            else None
        ),
    }


def _duplicate_summary(
    scoped: list[tuple[BusinessModel, BusinessNicheMembershipModel, float]],
) -> dict[str, Any]:
    domain_groups: defaultdict[str, list[str]] = defaultdict(list)
    phone_groups: defaultdict[str, list[str]] = defaultdict(list)
    for business, _, _ in scoped:
        domain = normalize_domain(business.domain or business.website_url)
        phone = normalize_phone(business.phone)
        if domain:
            domain_groups[domain].append(business.id)
        if phone:
            phone_groups[phone].append(business.id)
    return {
        "domain_groups": [
            {"value": value, "business_ids": ids}
            for value, ids in sorted(domain_groups.items())
            if len(ids) > 1
        ],
        "phone_groups": [
            {"value": value, "business_ids": ids}
            for value, ids in sorted(phone_groups.items())
            if len(ids) > 1
        ],
    }


def _attribute_value(fact: BusinessAttributeModel) -> Any:
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=utcnow().tzinfo)
    return value
