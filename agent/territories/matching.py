from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, literal, literal_column, or_, select
from sqlalchemy.orm import Session, aliased

from business_facts.repository import fact_value
from db.models import (
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    ContactModel,
    ProfileDeliveryItemModel,
    SourceObservationModel,
)
from shared.errors import ConflictError
from shared.utils import utcnow


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
    ) -> list[dict[str, Any]]:
        if not niche_ids or limit <= 0:
            return []
        cutoff = utcnow() - timedelta(days=profile.evidence_max_age_days)
        score = literal(0.0)
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
            .where(
                ~select(ProfileDeliveryItemModel.id)
                .where(
                    ProfileDeliveryItemModel.profile_id == profile.id,
                    ProfileDeliveryItemModel.business_id == BusinessModel.id,
                )
                .exists()
            )
        )

        if profile.trade_keys:
            statement = statement.where(
                or_(
                    BusinessModel.customer_kind == profile.customer_kind,
                    BusinessModel.customer_kind == "unknown",
                    BusinessModel.customer_kind.is_(None),
                )
            )
            score += case(
                (BusinessModel.customer_kind == profile.customer_kind, 2.0),
                else_=0.0,
            )

        exclusions = set(profile.exclusion_keys or [])
        if "closed" in exclusions:
            statement = statement.where(BusinessModel.status != "closed")
        for exclusion, field in EXCLUSION_FIELDS.items():
            if exclusion not in exclusions:
                continue
            statement = statement.where(or_(field.is_(False), field.is_(None)))
            score += case((field.is_(False), 1.0), else_=0.0)

        for signal in profile.signal_keys or []:
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
            score += case((_signal_condition(signal, fact), 10.0), else_=0.0)

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
                [fact.value_text, fact.value_number, fact.value_boolean]
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
        statement = statement.add_columns(score.label("profile_score"))
        if distance_sq is not None:
            statement = statement.add_columns(
                func.sqrt(distance_sq).label("distance_km")
            )
        else:
            statement = statement.add_columns(literal(None).label("distance_km"))
        statement = statement.group_by(*group_columns).order_by(
            score.desc(),
            literal_column_nulls_last("distance_km"),
            func.max(BusinessNicheMembershipModel.confidence).desc(),
            BusinessModel.id,
        ).limit(limit)

        ranked = self.session.execute(statement).mappings().all()
        return [
            self._result_row(
                business_id=str(item["id"]),
                score=float(item["profile_score"] or 0),
                distance_km=(
                    float(item["distance_km"])
                    if item["distance_km"] is not None
                    else None
                ),
                rank_position=rank_position,
                profile=profile,
                cutoff=cutoff,
            )
            for rank_position, item in enumerate(ranked, start=1)
        ]

    def _result_row(
        self,
        *,
        business_id: str,
        score: float,
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
                )
            )
        }
        contact = self.session.scalar(
            select(ContactModel)
            .where(ContactModel.business_id == business_id)
            .order_by(
                ContactModel.email.is_not(None).desc(),
                ContactModel.phone.is_not(None).desc(),
                ContactModel.last_seen_at.desc(),
            )
            .limit(1)
        )
        observation = self.session.scalar(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
            .limit(1)
        )
        signal_evidence = {
            signal: {
                "fact_key": fact_key,
                "value": fact_value(facts.get(fact_key)),
                "matched": _signal_fact_matches(signal, facts.get(fact_key)),
            }
            for signal, fact_key in SIGNAL_FACTS.items()
            if signal in set(profile.signal_keys or [])
        }
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
                "score": score,
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
        return fact.value_text.in_(("missing", "unavailable", "parked"))
    if signal in {"no_quote_flow", "no_contact_form"}:
        return fact.value_boolean.is_(False)
    if signal == "reviews_under_15":
        return fact.value_number < 15.0
    return literal(False)


def _signal_fact_matches(signal: str, fact: BusinessFactModel | None) -> bool:
    if fact is None:
        return False
    value = fact_value(fact)
    if signal == "website_unavailable":
        return value in {"missing", "unavailable", "parked"}
    if signal in {"no_quote_flow", "no_contact_form"}:
        return value is False
    if signal == "reviews_under_15":
        return isinstance(value, (int, float)) and value < 15
    return False


def literal_column_nulls_last(name: str):
    return literal_column(name).asc().nulls_last()
