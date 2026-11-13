from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, exists, func, literal, literal_column, or_, select
from sqlalchemy.orm import Session, aliased

from business_attributes.eligibility import (
    DEFAULT_MINIMUM_FACT_CONFIDENCE,
    eligible_fact_condition,
    fact_is_eligible,
)
from business_attributes.attribute_scoring import audience_match_config
from business_attributes.repository import attribute_value
from business_attributes.source_payloads import SOURCE_PAYLOAD_PREFIX
from business_index.eligibility import searchable_business_conditions
from canonical.normalization import (
    email_from_raw,
    normalize_email,
    normalize_phone,
    phone_from_raw,
)
from canonical.semantics import semantic_key
from db.models import (
    BusinessAttributeModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    SignalDefinitionModel,
)
from evaluation.outcome_learning import outcome_adjustment
from shared.errors import ConflictError
from shared.geospatial import haversine_distance_km_expression
from shared.utils import utcnow
from signal_validation.pitch_scope import pitch_scope_decision
from seeding.batches import active_membership_condition, observation_is_quarantined
from territories.opportunities import OPPORTUNITY_BY_KEY


SIGNAL_FACTS = {
    "website_unavailable": "website_status",
    "reviews_under_15": "google_review_count",
}

# Page-element detectors remain useful diagnostic attributes, but a shallow
# crawl must not turn their absence into a customer-facing website-upgrade
# lead.  Website upgrade matching is intentionally based on the composite
# website grade only.
WEBSITE_UPGRADE_SIGNAL_KEYS = frozenset({"website_quality_score"})
RETIRED_WEBSITE_UPGRADE_SIGNAL_KEYS = frozenset(
    {
        "mobile_viewport_present",
        "quote_or_booking_form_present",
        "contact_form_present",
        "primary_cta_present",
        "click_to_call_present",
        "no_quote_flow",
        "no_contact_form",
    }
)

LEGACY_SIGNAL_CONFIG = {
    "reviews_under_15": {
        "opportunity_threshold": 15,
        "minimum_confidence": 90,
    },
}


@dataclass(frozen=True)
class SignalMatchSpec:
    key: str
    attribute_key: str
    opportunity_direction: str
    config: dict[str, Any]


@dataclass(frozen=True)
class ServiceMatchSpec:
    key: str
    label: str
    signals: tuple[tuple[str, float], ...]

EXCLUSION_FIELDS = {
    "chains": BusinessModel.is_chain,
    "franchises": BusinessModel.is_franchise,
    "directories": BusinessModel.is_directory,
    "agencies": BusinessModel.is_agency,
}


class ProfileMatchService:
    """Select profile leads from persisted business attributes and facts only."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def match(
        self,
        *,
        profile,
        niche_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not niche_ids or limit <= 0:
            return []
        cutoff = utcnow() - timedelta(days=profile.evidence_max_age_days)
        outcome_weights: dict[str, float] = {}
        matched_signal_count = literal(0)
        confirmed_signal_count = literal(0)
        signal_conditions: list[Any] = []
        signal_aliases: dict[str, Any] = {}
        statement = (
            select(
                BusinessModel.id,
                func.max(BusinessNicheMembershipModel.confidence).label(
                    "membership_confidence"
                ),
            )
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .where(BusinessNicheMembershipModel.niche_id.in_(niche_ids))
            .where(active_membership_condition())
            .where(*searchable_business_conditions())
        )
        location_market_keys = _profile_location_market_keys(profile)
        if location_market_keys:
            statement = statement.where(
                BusinessNicheMembershipModel.market_key.in_(location_market_keys)
            )
        if profile.customer_kind != "both":
            statement = statement.where(BusinessModel.customer_kind == profile.customer_kind)

        if profile.min_google_rating is not None:
            statement = statement.where(
                _numeric_fact_exists(
                    business_id=BusinessModel.id,
                    attribute_key="google_rating",
                    cutoff=cutoff,
                    minimum=float(profile.min_google_rating),
                )
            )
        if profile.min_review_count is not None or profile.max_review_count is not None:
            statement = statement.where(
                _numeric_fact_exists(
                    business_id=BusinessModel.id,
                    attribute_key="google_review_count",
                    cutoff=cutoff,
                    minimum=(
                        float(profile.min_review_count)
                        if profile.min_review_count is not None
                        else None
                    ),
                    maximum=(
                        float(profile.max_review_count)
                        if profile.max_review_count is not None
                        else None
                    ),
                )
            )

        exclusions = set(profile.exclusion_keys or [])
        if "closed" in exclusions:
            statement = statement.where(BusinessModel.status != "closed")
        for exclusion, field in EXCLUSION_FIELDS.items():
            if exclusion not in exclusions:
                continue
            statement = statement.where(or_(field.is_(False), field.is_(None)))

        selected_signals = _selected_profile_signals(profile)
        signal_specs = self._signal_specs(selected_signals)
        service_specs = self._service_specs(profile.service_keys or [])
        signal_weights: dict[str, float] = {}
        for service in service_specs:
            for signal_key, weight in service.signals:
                signal_weights[signal_key] = max(
                    signal_weights.get(signal_key, 0.0),
                    weight,
                )
        weighted_match_score = literal(0.0)
        for spec in signal_specs:
            fact = aliased(BusinessAttributeModel, name=f"profile_fact_{spec.key}")
            signal_aliases[spec.key] = fact
            statement = statement.outerjoin(
                fact,
                and_(
                    fact.business_id == BusinessModel.id,
                    fact.attribute_key == spec.attribute_key,
                    fact.observed_at >= cutoff,
                    or_(fact.expires_at.is_(None), fact.expires_at >= utcnow()),
                ),
            )
            condition = _signal_condition(spec, fact)
            signal_conditions.append(condition)
            matched_signal_count += case((condition, 1), else_=0)
            weighted_match_score += case(
                (condition, signal_weights.get(spec.key, 1.0)),
                else_=0.0,
            )
            confirmed_signal_count += case(
                (_confirmed_signal_condition(spec, fact), 1),
                else_=0,
            )

        if selected_signals:
            statement = statement.where(
                or_(*signal_conditions) if signal_conditions else literal(False)
            )

        distance_km_expression = None
        if location_market_keys:
            distance_km_expression = None
        elif profile.latitude is not None and profile.longitude is not None:
            distance_km_expression = haversine_distance_km_expression(
                center_latitude=profile.latitude,
                center_longitude=profile.longitude,
                latitude=BusinessModel.latitude,
                longitude=BusinessModel.longitude,
            )
            statement = statement.where(
                BusinessModel.latitude.is_not(None),
                BusinessModel.longitude.is_not(None),
                distance_km_expression <= float(profile.radius_km),
            )
        elif profile.service_keys or profile.signal_keys:
            raise ConflictError(
                "profile market coordinates are unavailable",
                {"profile_id": profile.id, "city": profile.city},
            )
        else:
            statement = statement.where(BusinessModel.market_key == profile.market_key)

        group_columns = [BusinessModel.id]
        for fact in signal_aliases.values():
            group_columns.extend(
                [
                    # These columns are consumed by the eligibility predicate
                    # and its correlated validation subquery.  PostgreSQL
                    # requires every outer reference used by the grouped
                    # SELECT/ORDER BY expressions to be grouped explicitly;
                    # SQLite happens to accept the previous, incomplete set.
                    fact.id,
                    fact.business_id,
                    fact.attribute_key,
                    fact.value_type,
                    fact.value_text,
                    fact.value_number,
                    fact.value_boolean,
                    fact.confidence,
                    fact.attribute_score,
                    fact.score_version,
                    fact.expires_at,
                    fact.source,
                    fact.source_url,
                ]
            )
        group_columns.extend(
            [
                BusinessModel.customer_kind,
                BusinessModel.is_chain,
                BusinessModel.is_franchise,
                BusinessModel.is_directory,
                BusinessModel.is_agency,
            ]
        )
        if distance_km_expression is not None:
            group_columns.extend([BusinessModel.latitude, BusinessModel.longitude])
        statement = statement.add_columns(
            matched_signal_count.label("matched_signal_count"),
            confirmed_signal_count.label("confirmed_signal_count"),
            weighted_match_score.label("weighted_match_score"),
        )
        if distance_km_expression is not None:
            statement = statement.add_columns(distance_km_expression.label("distance_km"))
        else:
            statement = statement.add_columns(literal(None).label("distance_km"))
        # Fetch a bounded candidate pool before applying the evidence score in
        # Python. Freshness is intentionally evaluated against the stored fact
        # timestamps, rather than approximated in database-specific SQL.
        candidate_limit = min(max(limit * 4, 100), 400)
        statement = statement.group_by(*group_columns).order_by(
            confirmed_signal_count.desc(),
            weighted_match_score.desc(),
            matched_signal_count.desc(),
            literal_column_nulls_last("distance_km"),
            func.max(BusinessNicheMembershipModel.confidence).desc(),
            BusinessModel.id,
        ).limit(candidate_limit)

        ranked = self.session.execute(statement).mappings().all()
        results = [
            (
                self._result_row(
                    business_id=str(item["id"]),
                    matched_signal_count=int(item["matched_signal_count"] or 0),
                    confirmed_signal_count=int(item["confirmed_signal_count"] or 0),
                    weighted_match_score=float(item["weighted_match_score"] or 0),
                    distance_km=(
                        float(item["distance_km"])
                        if item["distance_km"] is not None
                        else None
                    ),
                    rank_position=rank_position,
                    profile=profile,
                    cutoff=cutoff,
                    signal_specs=signal_specs,
                    service_specs=service_specs,
                ),
                item,
            )
            for rank_position, item in enumerate(ranked, start=1)
        ]
        if outcome_weights:
            for result, _ in results:
                profile_match = result["raw"]["profile_match"]
                profile_match["outcome_adjustment"] = outcome_adjustment(
                    [
                        signal["signal_key"]
                        for signal in profile_match["matched_signals"]
                    ],
                    outcome_weights,
                )
        results.sort(key=_evidence_result_sort_key)
        final = [result for result, _ in results[:limit]]
        for rank_position, result in enumerate(final, start=1):
            result["raw"]["profile_match"]["rank_position"] = rank_position
        return final

    def _signal_specs(self, selected_signals: list[str]) -> list[SignalMatchSpec]:
        if not selected_signals:
            return []
        definitions = {
            definition.key: definition
            for definition in self.session.scalars(
                select(SignalDefinitionModel).where(
                    SignalDefinitionModel.key.in_(selected_signals),
                    SignalDefinitionModel.status.in_(("active", "derived")),
                )
            )
        }
        specs: list[SignalMatchSpec] = []
        for key in selected_signals:
            if key in SIGNAL_FACTS:
                specs.append(
                    SignalMatchSpec(
                        key=key,
                        attribute_key=SIGNAL_FACTS[key],
                        opportunity_direction="legacy",
                        config=audience_match_config(
                            SIGNAL_FACTS[key],
                            "lower_is_opportunity" if key == "reviews_under_15" else "legacy",
                            LEGACY_SIGNAL_CONFIG.get(key, {}),
                        ),
                    )
                )
                continue
            definition = definitions.get(key)
            if definition is not None and definition.opportunity_direction != "none":
                specs.append(
                    SignalMatchSpec(
                        key=key,
                        attribute_key=definition.key,
                        opportunity_direction=definition.opportunity_direction,
                        config=audience_match_config(
                            definition.key,
                            definition.opportunity_direction,
                            definition.config or {},
                        ),
                    )
                )
        return specs

    def _service_specs(self, selected_services: list[str]) -> list[ServiceMatchSpec]:
        return [
            ServiceMatchSpec(
                key=criterion.key,
                label=criterion.label,
                signals=((criterion.attribute_key, criterion.weight),),
            )
            for key in selected_services
            if (criterion := OPPORTUNITY_BY_KEY.get(key)) is not None
        ]
    def _result_row(
        self,
        *,
        business_id: str,
        matched_signal_count: int,
        confirmed_signal_count: int,
        weighted_match_score: float,
        distance_km: float | None,
        rank_position: int,
        profile,
        cutoff: datetime,
        signal_specs: list[SignalMatchSpec],
        service_specs: list[ServiceMatchSpec],
    ) -> dict[str, Any]:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise ValueError(f"business not found during profile match: {business_id}")
        facts = {
            fact.attribute_key: fact
            for fact in self.session.scalars(
                select(BusinessAttributeModel).where(
                    BusinessAttributeModel.business_id == business_id,
                    BusinessAttributeModel.observed_at >= cutoff,
                    or_(
                        BusinessAttributeModel.expires_at.is_(None),
                        BusinessAttributeModel.expires_at >= utcnow(),
                    ),
                )
            )
        }
        observations = [
            candidate
            for candidate in self.session.scalars(
                select(BusinessAttributeModel)
                .where(
                    BusinessAttributeModel.business_id == business_id,
                    BusinessAttributeModel.attribute_key.startswith(SOURCE_PAYLOAD_PREFIX),
                )
                .order_by(BusinessAttributeModel.observed_at.desc())
            )
            if not observation_is_quarantined(self.session, candidate)
        ]
        contact = next(
            (
                candidate
                for candidate in self.session.scalars(
                    select(ContactModel)
                    .where(ContactModel.business_id == business_id)
                    .order_by(
                        ContactModel.email.is_not(None).desc(),
                        ContactModel.phone.is_not(None).desc(),
                        ContactModel.last_seen_at.desc(),
                    )
                )
                if _contact_has_active_support(candidate, business, observations)
            ),
            None,
        )
        signal_evidence = {}
        for spec in signal_specs:
            fact = facts.get(spec.attribute_key)
            minimum_confidence = int(
                spec.config.get(
                    "minimum_confidence", DEFAULT_MINIMUM_FACT_CONFIDENCE
                )
            )
            eligible = fact_is_eligible(
                fact,
                minimum_confidence=minimum_confidence,
                require_provenance=True,
            )
            match_confidence = _signal_match_confidence(spec, fact)
            fact_observation = fact
            evidence = {
                "attribute_key": spec.attribute_key,
                "value": attribute_value(fact),
                "evaluated": eligible and fact.attribute_score is not None,
                "matched": match_confidence is not None,
                "confidence": match_confidence,
                "evidence_confidence": fact.confidence if fact is not None else None,
                "opportunity_score": fact.attribute_score if fact is not None else None,
            }
            if fact_observation is not None:
                pitch_eligible, pitch_reason = pitch_scope_decision(
                    spec.attribute_key,
                    attribute_value(fact),
                    fact_observation.raw_payload or {},
                )
                evidence.update(
                    {
                        "attribute_id": fact_observation.id,
                        "source": fact_observation.source,
                        "source_url": fact_observation.source_url,
                        "observed_at": fact_observation.observed_at.isoformat(),
                        "pitch_eligible": pitch_eligible,
                        "pitch_reason": pitch_reason,
                    }
                )
            else:
                evidence.update(
                    {
                        "pitch_eligible": False,
                        "pitch_reason": "Finding has no source observation.",
                    }
                )
            signal_evidence[spec.key] = evidence
        matched_signals = [
            {
                "signal_key": signal,
                "attribute_key": evidence["attribute_key"],
                "value": evidence["value"],
                "confidence": evidence["confidence"],
                "evidence_confidence": evidence["evidence_confidence"],
                "opportunity_score": evidence["opportunity_score"],
                "pitch_eligible": evidence["pitch_eligible"],
                "pitch_reason": evidence["pitch_reason"],
                **(
                    {
                        "attribute_id": evidence["attribute_id"],
                        "source": evidence["source"],
                        "source_url": evidence["source_url"],
                        "observed_at": evidence["observed_at"],
                    }
                    if evidence.get("attribute_id")
                    else {}
                ),
            }
            for signal, evidence in signal_evidence.items()
            if evidence["matched"] is True
        ]
        matched_observations = [
            facts[item["attribute_key"]]
            for item in matched_signals
            if item.get("attribute_key") in facts
        ]
        observation = (
            matched_observations[0]
            if matched_observations
            else observations[0]
            if observations
            else None
        )
        matched_services = []
        for service in service_specs:
            total_weight = sum(weight for _, weight in service.signals)
            evaluated_weight = sum(
                weight
                for signal_key, weight in service.signals
                if signal_key in signal_evidence
                and signal_evidence[signal_key]["evaluated"] is True
            )
            weighted_opportunity = sum(
                weight * float(signal_evidence[signal_key]["opportunity_score"] or 0.0)
                for signal_key, weight in service.signals
                if signal_key in signal_evidence
                and signal_evidence[signal_key]["evaluated"] is True
            )
            supporting_evidence = [
                {
                    "signal_key": signal_key,
                    "attribute_key": signal_evidence[signal_key]["attribute_key"],
                    "value": signal_evidence[signal_key]["value"],
                    "confidence": signal_evidence[signal_key]["confidence"],
                    "weight": weight,
                }
                for signal_key, weight in service.signals
                if signal_key in signal_evidence
                and signal_evidence[signal_key]["matched"] is True
            ]
            if supporting_evidence:
                matched_services.append(
                    {
                        "service_key": service.key,
                        "label": service.label,
                        "score": round(
                            sum(float(item["weight"]) for item in supporting_evidence),
                            3,
                        ),
                        "composite_score": round(
                            weighted_opportunity / total_weight,
                            1,
                        ) if total_weight else 0.0,
                        "measured_score": round(
                            weighted_opportunity / evaluated_weight,
                            1,
                        ),
                        "coverage": round(evaluated_weight / total_weight, 3)
                        if total_weight
                        else 0.0,
                        "matched_weight": round(
                            sum(float(item["weight"]) for item in supporting_evidence),
                            3,
                        ),
                        "supporting_evidence": supporting_evidence,
                    }
                )
        composite_service_score = max(
            (float(item["composite_score"]) for item in matched_services),
            default=0.0,
        )
        classifications = {
            "customer_kind": business.customer_kind,
            "is_chain": business.is_chain,
            "is_franchise": business.is_franchise,
            "is_directory": business.is_directory,
            "is_agency": business.is_agency,
        }
        opportunity_score, score_breakdown = _opportunity_score(
            {
                spec.key: {
                    "matched": signal_evidence[spec.key]["matched"],
                    "confidence_score": (
                        facts[spec.attribute_key].confidence
                        if spec.attribute_key in facts
                        else None
                    ),
                    "observed_at": (
                        facts[spec.attribute_key].observed_at.isoformat()
                        if spec.attribute_key in facts
                        else None
                    ),
                    "severity": _signal_severity(
                        spec,
                        service_specs,
                        facts[spec.attribute_key].attribute_score
                        if spec.attribute_key in facts
                        else None,
                    ),
                }
                for spec in signal_specs
            },
            now=utcnow(),
            max_age_days=profile.evidence_max_age_days,
        )
        opportunity_checks = [
            {
                "key": spec.key,
                "attribute_key": spec.attribute_key,
                "state": (
                    "verified"
                    if signal_evidence[spec.key]["matched"]
                    else "not_evaluated"
                    if facts.get(spec.attribute_key) is None
                    else "no_gap"
                ),
                "value": signal_evidence[spec.key]["value"],
                "evidence_confidence": signal_evidence[spec.key][
                    "evidence_confidence"
                ],
            }
            for spec in signal_specs
        ]
        evaluated_count = sum(
            item["state"] != "not_evaluated" for item in opportunity_checks
        )
        lead_assessment = {
            "lead_state": "qualified",
            "eligibility": {
                "state": "target",
                "reasons": [],
            },
            "opportunities": opportunity_checks,
            "verified_opportunity_count": sum(
                item["state"] == "verified" for item in opportunity_checks
            ),
            "evidence_coverage": {
                "state": (
                    "complete"
                    if evaluated_count == len(opportunity_checks)
                    else "partial"
                    if evaluated_count
                    else "missing"
                ),
                "evaluated": evaluated_count,
                "required": len(opportunity_checks),
            },
        }
        raw = {
            **(observation.raw_payload if observation else {}),
            "match_origin": "profile_sql",
            "canonical_business_id": business.id,
            "source_attribute_id": observation.id if observation else None,
            "business_attributes": {
                key: attribute_value(value) for key, value in facts.items()
            },
            "profile_match": {
                "status": "matched",
                "score": matched_signal_count,
                "service_score": round(weighted_match_score, 3),
                "website_improvement_score": round(composite_service_score, 1),
                "opportunity_score": opportunity_score,
                "score_breakdown": score_breakdown,
                "lead_assessment": lead_assessment,
                "selected_signal_count": len(signal_evidence),
                "matched_signal_count": matched_signal_count,
                "confirmed_signal_count": confirmed_signal_count,
                "possible_signal_count": matched_signal_count - confirmed_signal_count,
                "matched_signals": matched_signals,
                "matched_services": matched_services,
                "rank_position": rank_position,
                "distance_km": round(distance_km, 2) if distance_km is not None else None,
                "location_evidence": (
                    "coordinates" if distance_km is not None else "market_key"
                ),
                "classifications": classifications,
                "signals": signal_evidence,
            },
            "search_match": {
                "status": "matched",
                "reason": (
                    "Eligible target business with at least one verified selected opportunity."
                ),
            },
        }
        return {
            "title": business.display_name,
            "url": business.website_url,
            "snippet": business.semantic_text,
            "geography": business.geography or business.address,
            "contact_email": contact.email if contact else None,
            "source": observation.source if observation else "business_index",
            "raw": raw,
        }


def _profile_location_market_keys(profile) -> list[str]:
    keys: list[str] = []
    for location in profile.locations or []:
        # Existing index memberships were stored with the city key (for
        # example, ``toronto``), while canonical place selection stores the
        # full label (``Toronto, Ontario, Canada``).  Keep both aliases so a
        # saved search can read the shared index regardless of which version
        # created the membership.
        for value in (location.get("city"), location.get("label")):
            text = str(value or "")
            aliases = (
                semantic_key(text),
                semantic_key(
                    "".join(
                        character
                        for character in unicodedata.normalize("NFKD", text)
                        if not unicodedata.combining(character)
                    )
                ),
            )
            for key in aliases:
                if key and key not in keys:
                    keys.append(key)
    return keys


def _selected_profile_signals(profile) -> list[str]:
    selected = list(dict.fromkeys(profile.signal_keys or []))
    if "website_upgrade" not in set(profile.service_keys or []):
        return selected
    retained = [
        signal
        for signal in selected
        if signal
        not in RETIRED_WEBSITE_UPGRADE_SIGNAL_KEYS | WEBSITE_UPGRADE_SIGNAL_KEYS
    ]
    return [*retained, *WEBSITE_UPGRADE_SIGNAL_KEYS]


def _signal_condition(spec: SignalMatchSpec, fact) -> Any:
    evidence = _usable_evidence_condition(spec, fact)
    minimum_score = float(spec.config.get("audience_min_score", 50.001))
    return and_(
        evidence,
        fact.attribute_score.is_not(None),
        fact.attribute_score >= minimum_score,
    )


def _confirmed_signal_condition(spec: SignalMatchSpec, fact) -> Any:
    return _signal_condition(spec, fact)


def _usable_evidence_condition(
    spec: SignalMatchSpec,
    fact,
) -> Any:
    return eligible_fact_condition(
        fact,
        minimum_confidence=int(
            spec.config.get("minimum_confidence", DEFAULT_MINIMUM_FACT_CONFIDENCE)
        ),
        require_provenance=True,
        # Publication is the eligibility stamp. Requiring a second validation
        # row here duplicated that decision and hid otherwise publishable facts.
        require_validation=False,
    )


def _numeric_fact_exists(
    *,
    business_id,
    attribute_key: str,
    cutoff: datetime,
    minimum: float | None = None,
    maximum: float | None = None,
) -> Any:
    """Require current, publishable numeric evidence for an explicit search filter."""
    fact = aliased(BusinessAttributeModel, name=f"filter_fact_{attribute_key}")
    conditions: list[Any] = [
        fact.business_id == business_id,
        fact.attribute_key == attribute_key,
        fact.value_number.is_not(None),
        fact.observed_at >= cutoff,
        or_(fact.expires_at.is_(None), fact.expires_at >= utcnow()),
        eligible_fact_condition(
            fact,
            minimum_confidence=DEFAULT_MINIMUM_FACT_CONFIDENCE,
            require_provenance=True,
            require_validation=False,
        ),
    ]
    if minimum is not None:
        conditions.append(fact.value_number >= minimum)
    if maximum is not None:
        conditions.append(fact.value_number <= maximum)
    return exists(select(fact.id).where(*conditions))


def _signal_match_confidence(
    spec: SignalMatchSpec,
    fact: BusinessAttributeModel | None,
) -> str | None:
    if not fact_is_eligible(
        fact,
        minimum_confidence=int(
            spec.config.get("minimum_confidence", DEFAULT_MINIMUM_FACT_CONFIDENCE)
        ),
        require_provenance=True,
    ):
        return None
    evidence_confidence = "confirmed"
    minimum_score = float(spec.config.get("audience_min_score", 50.001))
    return (
        evidence_confidence
        if fact.attribute_score is not None and fact.attribute_score >= minimum_score
        else None
    )


def _contact_has_active_support(
    contact: ContactModel,
    business: BusinessModel,
    observations: list[BusinessAttributeModel],
) -> bool:
    supported_phones = {
        value
        for value in [normalize_phone(business.phone)]
        + [phone_from_raw(observation.raw_payload) for observation in observations]
        if value
    }
    supported_emails = {
        value
        for value in [email_from_raw(observation.raw_payload) for observation in observations]
        if value
    }
    phone = normalize_phone(contact.phone)
    email = normalize_email(contact.email)
    return bool(
        (phone and phone in supported_phones)
        or (email and email in supported_emails)
    )


def _evidence_result_sort_key(item: tuple[dict[str, Any], Any]) -> tuple:
    result, row = item
    profile_match = result["raw"]["profile_match"]
    distance = profile_match.get("distance_km")
    matched_signals = profile_match.get("matched_signals") or []
    verified_missing_website = any(
        signal.get("attribute_key") == "website_status"
        and signal.get("value") == "missing"
        for signal in matched_signals
    )
    return (
        # When both website options are selected, a verified missing website is
        # always the strongest opportunity. Composite upgrade evidence orders
        # the remaining candidates before distance is used as a tie-breaker.
        0 if verified_missing_website else 1,
        -float(profile_match.get("website_improvement_score") or 0.0),
        -float(profile_match.get("opportunity_score") or 0.0),
        -float(profile_match.get("service_score") or 0.0),
        -int(profile_match.get("confirmed_signal_count") or 0),
        -int(profile_match.get("matched_signal_count") or 0),
        -float(profile_match.get("outcome_adjustment") or 0.0),
        float(distance) if isinstance(distance, (int, float)) else float("inf"),
        -float(row.get("membership_confidence") or 0.0),
        str(row["id"]),
    )


def _signal_severity(
    spec: SignalMatchSpec,
    service_specs: list[ServiceMatchSpec],
    opportunity_score: float | None,
) -> float:
    # Opportunity severity uses the same direction as every other consumer.
    if opportunity_score is not None:
        return round(1.0 + 4.0 * max(0.0, min(100.0, opportunity_score)) / 100.0, 2)
    configured = spec.config.get("opportunity_severity")
    if isinstance(configured, (int, float)):
        return round(max(1.0, min(5.0, float(configured))), 2)
    weights = [
        weight
        for service in service_specs
        for signal_key, weight in service.signals
        if signal_key == spec.key
    ]
    if not weights:
        return 3.0
    # Service mappings already express relative importance. Keep the public
    # severity scale stable even if an administrator supplies a large weight.
    return round(max(1.0, min(5.0, 2.0 + max(weights))), 2)


def _opportunity_score(
    signal_evidence: dict[str, dict[str, Any]],
    *,
    now: datetime,
    max_age_days: int,
) -> tuple[float, dict[str, float]]:
    matched = [evidence for evidence in signal_evidence.values() if evidence["matched"]]
    if not matched:
        return 0.0, {"severity": 0.0, "confidence": 0.0, "freshness": 0.0}
    severity = sum(float(item["severity"]) / 5.0 for item in matched) / len(matched)
    confidence = sum(
        max(0.0, min(100.0, float(item["confidence_score"] or 0.0))) / 100.0
        for item in matched
    ) / len(matched)
    freshness_values: list[float] = []
    for item in matched:
        observed_at = item.get("observed_at")
        if not observed_at:
            freshness_values.append(0.0)
            continue
        observed = datetime.fromisoformat(str(observed_at))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=now.tzinfo)
        age_days = max(0.0, (now - observed).total_seconds() / 86400)
        freshness_values.append(max(0.0, 1.0 - age_days / max(1, max_age_days)))
    freshness = sum(freshness_values) / len(freshness_values)
    breakdown = {
        "severity": round(severity * 40.0 + min(10.0, (len(matched) - 1) * 5.0), 1),
        "confidence": round(confidence * 30.0, 1),
        "freshness": round(freshness * 20.0, 1),
    }
    return round(sum(breakdown.values()), 1), breakdown


def literal_column_nulls_last(name: str):
    return literal_column(name).asc().nulls_last()

