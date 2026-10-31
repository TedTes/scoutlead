from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from business_index.eligibility import REQUIRED_VALIDATIONS
from canonical.normalization import normalize_domain, normalize_phone
from db.models import (
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    NicheModel,
    SourceObservationModel,
    ValidationResultModel,
)
from shared.geospatial import haversine_distance_km
from shared.utils import utcnow
from source_observations.integrity import evaluate_observation_integrity


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
    validations = _group_by_business(
        session.scalars(
            select(ValidationResultModel)
            .where(ValidationResultModel.business_id.in_(business_ids))
            .order_by(
                ValidationResultModel.observed_at.desc(),
                ValidationResultModel.created_at.desc(),
                ValidationResultModel.id.desc(),
            )
        )
        if business_ids
        else []
    )
    observations = _group_by_business(
        session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id.in_(business_ids))
            .order_by(SourceObservationModel.observed_at.desc())
        )
        if business_ids
        else []
    )
    facts = _group_by_business(
        session.scalars(
            select(BusinessFactModel)
            .where(BusinessFactModel.business_id.in_(business_ids))
            .order_by(BusinessFactModel.fact_key)
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
        current = _latest_scoped_validations(
            validations.get(business.id, []),
            niche_id=niche.id,
            market_key=membership.market_key,
            now=checked_at,
        )
        state, reasons = _quality_state(business, current)
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
                validations=current,
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
                "required_validations": dict(REQUIRED_VALIDATIONS),
                "unknown_is_publishable": False,
                "failed_is_publishable": False,
                "only_validated_records_are_searchable": True,
            },
        },
        **buckets,
    }


def _group_by_business(rows: Iterable[Any]) -> dict[str, list[Any]]:
    grouped: defaultdict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[str(row.business_id)].append(row)
    return grouped


def _latest_scoped_validations(
    rows: list[ValidationResultModel],
    *,
    niche_id: str,
    market_key: str,
    now: datetime,
) -> dict[str, ValidationResultModel]:
    scoped = [
        row
        for row in rows
        if _aware(row.expires_at) >= _aware(now)
        and row.niche_id in {None, niche_id}
        and row.market_key in {None, market_key}
    ]
    scoped.sort(
        key=lambda row: (
            row.niche_id == niche_id,
            row.market_key == market_key,
            _aware(row.observed_at),
            _aware(row.created_at),
            row.id,
        ),
        reverse=True,
    )
    latest: dict[str, ValidationResultModel] = {}
    for row in scoped:
        latest.setdefault(row.validation_type, row)
    return latest


def _quality_state(
    business: BusinessModel,
    validations: dict[str, ValidationResultModel],
) -> tuple[str, list[str]]:
    if business.status != "active":
        return "rejected", [f"Business status is {business.status}."]
    failed = [
        (validation_type, validations.get(validation_type))
        for validation_type in REQUIRED_VALIDATIONS
        if validations.get(validation_type) is not None
        and validations[validation_type].status == "failed"
    ]
    if failed:
        return "rejected", [
            f"{validation_type}: {row.reason}"
            for validation_type, row in failed
            if row is not None
        ]
    reasons = []
    for validation_type, minimum_confidence in REQUIRED_VALIDATIONS.items():
        row = validations.get(validation_type)
        if row is None:
            reasons.append(f"Missing current {validation_type} validation.")
        elif row.status != "passed":
            reasons.append(f"{validation_type} validation is {row.status}: {row.reason}")
        elif row.confidence < minimum_confidence:
            reasons.append(
                f"{validation_type} confidence {row.confidence} is below {minimum_confidence}."
            )
    if reasons:
        return "uncertain", reasons
    return "validated", ["All required current validations passed."]


def _business_record(
    business: BusinessModel,
    *,
    membership: BusinessNicheMembershipModel,
    distance_km: float,
    quality_state: str,
    quality_reasons: list[str],
    validations: dict[str, ValidationResultModel],
    observations: list[SourceObservationModel],
    observation_summary: dict[str, Any],
    facts: list[BusinessFactModel],
    contacts: list[ContactModel],
    now: datetime,
) -> dict[str, Any]:
    signal_validations = {
        key.removeprefix("signal:"): row
        for key, row in validations.items()
        if key.startswith("signal:")
    }
    eligible_facts = []
    for fact in facts:
        validation = signal_validations.get(fact.fact_key)
        eligible = bool(
            fact.quality_state == "published"
            and fact.resolution_state == "confirmed"
            and fact.confidence >= 90
            and fact.expires_at is not None
            and _aware(fact.expires_at) > _aware(now)
            and fact.source_observation_id
            and validation is not None
            and validation.status == "passed"
            and validation.confidence >= 90
            and validation.source_observation_id == fact.source_observation_id
        )
        eligible_facts.append(
            {
                "key": fact.fact_key,
                "value": _fact_value(fact),
                "confidence": fact.confidence,
                "quality_state": fact.quality_state,
                "resolution_state": fact.resolution_state,
                "observed_at": fact.observed_at.isoformat(),
                "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
                "source_observation_id": fact.source_observation_id,
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
            "source_observation_id": membership.source_observation_id,
        },
        "quality": {
            "state": quality_state,
            "reasons": quality_reasons,
            "validations": {
                key: {
                    "status": row.status,
                    "confidence": row.confidence,
                    "reason": row.reason,
                    "observed_at": row.observed_at.isoformat(),
                    "expires_at": row.expires_at.isoformat(),
                    "source_observation_id": row.source_observation_id,
                }
                for key, row in sorted(validations.items())
            },
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
    observations: list[SourceObservationModel],
    *,
    now: datetime,
) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    for observation in observations:
        result = evaluate_observation_integrity(observation, now=now, require_locator=True)
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


def _fact_value(fact: BusinessFactModel) -> Any:
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=utcnow().tzinfo)
    return value
