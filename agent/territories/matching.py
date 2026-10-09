from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, literal, literal_column, or_, select
from sqlalchemy.orm import Session, aliased

from business_facts.repository import fact_value
from canonical.normalization import (
    email_from_raw,
    normalize_email,
    normalize_phone,
    phone_from_raw,
)
from db.models import (
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    BusinessPublicationModel,
    ContactModel,
    OutcomeModel,
    ProfileDeliveryItemModel,
    SourceObservationModel,
)
from evaluation.outcome_learning import MIN_CONTACTED, MIN_POSITIVE, outcome_adjustment
from shared.errors import ConflictError
from shared.utils import utcnow
from seeding.batches import active_membership_condition, observation_is_quarantined


SIGNAL_FACTS = {
    "website_unavailable": "website_status",
    "no_quote_flow": "quote_or_booking_form_present",
    "no_contact_form": "contact_form_present",
    "reviews_under_15": "google_review_count",
}

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
        exclude_legacy_deliveries: bool = True,
    ) -> list[dict[str, Any]]:
        if not niche_ids or limit <= 0:
            return []
        cutoff = utcnow() - timedelta(days=profile.evidence_max_age_days)
        outcome_weights = self._active_outcome_weights(
            workspace_id=profile.workspace_id,
            product_id=profile.product_id,
            niche_ids=niche_ids,
        )
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
            .join(
                BusinessPublicationModel,
                and_(
                    BusinessPublicationModel.business_id == BusinessModel.id,
                    BusinessPublicationModel.niche_id
                    == BusinessNicheMembershipModel.niche_id,
                    BusinessPublicationModel.market_key
                    == BusinessNicheMembershipModel.market_key,
                    BusinessPublicationModel.status == "published",
                    or_(
                        BusinessPublicationModel.expires_at.is_(None),
                        BusinessPublicationModel.expires_at >= utcnow(),
                    ),
                ),
            )
            .where(BusinessNicheMembershipModel.niche_id.in_(niche_ids))
            .where(active_membership_condition())
        )
        if exclude_legacy_deliveries:
            statement = statement.where(
                ~select(ProfileDeliveryItemModel.id)
                .where(
                    ProfileDeliveryItemModel.profile_id == profile.id,
                    ProfileDeliveryItemModel.business_id == BusinessModel.id,
                )
                .exists()
            )

        if profile.trade_keys:
            statement = statement.where(
                or_(
                    BusinessModel.customer_kind == profile.customer_kind,
                    BusinessModel.customer_kind == "unknown",
                    BusinessModel.customer_kind.is_(None),
                )
            )

        exclusions = set(profile.exclusion_keys or [])
        if "closed" in exclusions:
            statement = statement.where(BusinessModel.status != "closed")
        for exclusion, field in EXCLUSION_FIELDS.items():
            if exclusion not in exclusions:
                continue
            statement = statement.where(or_(field.is_(False), field.is_(None)))

        selected_signals = list(dict.fromkeys(profile.signal_keys or []))
        for signal in selected_signals:
            fact_key = SIGNAL_FACTS.get(signal)
            if fact_key is None:
                continue
            fact = aliased(BusinessFactModel, name=f"profile_fact_{signal}")
            signal_aliases[signal] = fact
            statement = statement.outerjoin(
                fact,
                and_(
                    fact.business_id == BusinessModel.id,
                    fact.fact_key == fact_key,
                    fact.observed_at >= cutoff,
                    or_(fact.expires_at.is_(None), fact.expires_at >= utcnow()),
                ),
            )
            condition = _signal_condition(signal, fact)
            signal_conditions.append(condition)
            matched_signal_count += case((condition, 1), else_=0)
            confirmed_signal_count += case(
                (_confirmed_signal_condition(signal, fact), 1),
                else_=0,
            )

        if selected_signals:
            statement = statement.where(
                or_(*signal_conditions) if signal_conditions else literal(False)
            )

        distance_sq = None
        if profile.latitude is not None and profile.longitude is not None:
            lat_km = (BusinessModel.latitude - profile.latitude) * 111.32
            lng_km = (
                (BusinessModel.longitude - profile.longitude)
                * 111.32
                * func.cos(func.radians(profile.latitude))
            )
            distance_sq = lat_km * lat_km + lng_km * lng_km
            statement = statement.where(
                BusinessModel.latitude.is_not(None),
                BusinessModel.longitude.is_not(None),
                distance_sq <= float(profile.radius_km * profile.radius_km),
            )
        elif profile.trade_keys:
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
                    fact.value_text,
                    fact.value_number,
                    fact.value_boolean,
                    fact.confidence,
                    fact.resolution_state,
                    fact.quality_state,
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
        if distance_sq is not None:
            group_columns.extend([BusinessModel.latitude, BusinessModel.longitude])
        statement = statement.add_columns(
            matched_signal_count.label("matched_signal_count"),
            confirmed_signal_count.label("confirmed_signal_count"),
        )
        if distance_sq is not None:
            statement = statement.add_columns(
                func.sqrt(distance_sq).label("distance_km")
            )
        else:
            statement = statement.add_columns(literal(None).label("distance_km"))
        candidate_limit = min(max(limit * 4, 100), 400) if outcome_weights else limit
        statement = statement.group_by(*group_columns).order_by(
            confirmed_signal_count.desc(),
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
                    distance_km=(
                        float(item["distance_km"])
                        if item["distance_km"] is not None
                        else None
                    ),
                    rank_position=rank_position,
                    profile=profile,
                    cutoff=cutoff,
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
            results.sort(key=_learned_result_sort_key)
        final = [result for result, _ in results[:limit]]
        for rank_position, result in enumerate(final, start=1):
            result["raw"]["profile_match"]["rank_position"] = rank_position
        return final

    def _active_outcome_weights(
        self,
        *,
        workspace_id: str,
        product_id: str,
        niche_ids: list[str],
    ) -> dict[str, float]:
        models = list(
            self.session.scalars(
                select(OutcomeModel).where(
                    OutcomeModel.workspace_id == workspace_id,
                    OutcomeModel.product_id == product_id,
                    OutcomeModel.niche_id.in_(niche_ids),
                    OutcomeModel.n_contacted >= MIN_CONTACTED,
                    OutcomeModel.n_positive >= MIN_POSITIVE,
                )
            )
        )
        if not models:
            return {}
        totals: dict[str, float] = {}
        sample_counts: dict[str, int] = {}
        for model in models:
            for signal, weight in (model.weights or {}).items():
                totals[signal] = totals.get(signal, 0.0) + float(weight) * model.n_contacted
                sample_counts[signal] = sample_counts.get(signal, 0) + model.n_contacted
        return {
            signal: total / sample_counts[signal]
            for signal, total in totals.items()
            if sample_counts[signal]
        }

    def _result_row(
        self,
        *,
        business_id: str,
        matched_signal_count: int,
        confirmed_signal_count: int,
        distance_km: float | None,
        rank_position: int,
        profile,
        cutoff: datetime,
    ) -> dict[str, Any]:
        business = self.session.get(BusinessModel, business_id)
        if business is None:
            raise ValueError(f"business not found during profile match: {business_id}")
        facts = {
            fact.fact_key: fact
            for fact in self.session.scalars(
                select(BusinessFactModel).where(
                    BusinessFactModel.business_id == business_id,
                    BusinessFactModel.observed_at >= cutoff,
                    or_(
                        BusinessFactModel.expires_at.is_(None),
                        BusinessFactModel.expires_at >= utcnow(),
                    ),
                )
            )
        }
        observations = [
            candidate
            for candidate in self.session.scalars(
                select(SourceObservationModel)
                .where(SourceObservationModel.business_id == business_id)
                .order_by(SourceObservationModel.observed_at.desc())
            )
            if not observation_is_quarantined(self.session, candidate)
        ]
        observation = observations[0] if observations else None
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
        signal_evidence = {
            signal: {
                "fact_key": fact_key,
                "value": fact_value(facts.get(fact_key)),
                "matched": _signal_match_confidence(signal, facts.get(fact_key)) is not None,
                "confidence": _signal_match_confidence(signal, facts.get(fact_key)),
            }
            for signal, fact_key in SIGNAL_FACTS.items()
            if signal in set(profile.signal_keys or [])
        }
        matched_signals = [
            {
                "signal_key": signal,
                "fact_key": evidence["fact_key"],
                "value": evidence["value"],
            }
            for signal, evidence in signal_evidence.items()
            if evidence["matched"] is True
        ]
        classifications = {
            "customer_kind": business.customer_kind,
            "is_chain": business.is_chain,
            "is_franchise": business.is_franchise,
            "is_directory": business.is_directory,
            "is_agency": business.is_agency,
        }
        raw = {
            **(observation.raw_payload if observation else {}),
            "match_origin": "profile_sql",
            "canonical_business_id": business.id,
            "source_observation_id": observation.id if observation else None,
            "business_facts": {
                key: fact_value(value) for key, value in facts.items()
            },
            "profile_match": {
                "status": "matched",
                "score": matched_signal_count,
                "selected_signal_count": len(signal_evidence),
                "matched_signal_count": matched_signal_count,
                "confirmed_signal_count": confirmed_signal_count,
                "possible_signal_count": matched_signal_count - confirmed_signal_count,
                "matched_signals": matched_signals,
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
                "reason": "Matched persisted audience fields and business facts.",
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


def _signal_condition(signal: str, fact) -> Any:
    if signal == "website_unavailable":
        return and_(
            fact.resolution_state == "confirmed",
            fact.quality_state == "published",
            fact.confidence >= 90,
            fact.value_text.in_(("missing", "unavailable", "parked")),
        )
    if signal in {"no_quote_flow", "no_contact_form"}:
        return and_(
            fact.resolution_state == "confirmed",
            fact.quality_state == "published",
            fact.confidence >= 90,
            fact.value_boolean.is_(False),
        )
    if signal == "reviews_under_15":
        return and_(
            fact.resolution_state == "confirmed",
            fact.quality_state == "published",
            fact.confidence >= 90,
            fact.value_number < 15.0,
        )
    return literal(False)


def _confirmed_signal_condition(signal: str, fact) -> Any:
    return _signal_condition(signal, fact)


def _signal_match_confidence(
    signal: str,
    fact: BusinessFactModel | None,
) -> str | None:
    if fact is None:
        return None
    if (
        fact.resolution_state != "confirmed"
        or fact.quality_state != "published"
        or fact.confidence < 90
    ):
        return None
    value = fact_value(fact)
    if signal == "website_unavailable":
        return "confirmed" if value in {"missing", "unavailable", "parked"} else None
    if signal in {"no_quote_flow", "no_contact_form"}:
        return "confirmed" if value is False else None
    if signal == "reviews_under_15":
        return "confirmed" if isinstance(value, (int, float)) and value < 15 else None
    return None


def _contact_has_active_support(
    contact: ContactModel,
    business: BusinessModel,
    observations: list[SourceObservationModel],
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


def _learned_result_sort_key(item: tuple[dict[str, Any], Any]) -> tuple:
    result, row = item
    profile_match = result["raw"]["profile_match"]
    distance = profile_match.get("distance_km")
    return (
        -int(profile_match.get("confirmed_signal_count") or 0),
        -int(profile_match.get("matched_signal_count") or 0),
        -float(profile_match.get("outcome_adjustment") or 0.0),
        float(distance) if isinstance(distance, (int, float)) else float("inf"),
        -float(row.get("membership_confidence") or 0.0),
        str(row["id"]),
    )


def literal_column_nulls_last(name: str):
    return literal_column(name).asc().nulls_last()
