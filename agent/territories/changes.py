from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.models import (
    BusinessFactChangeModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
)
from seeding.batches import active_membership_condition
from territories.profile_catalog import profile_trade_spec
from territories.repository import TerritoryRepository


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


class ProfileChangeKind(StrEnum):
    ENTERED = "entered"
    EXITED = "exited"
    UPDATED = "updated"


class ProfileFactChangeRead(BaseModel):
    id: str
    business_id: str
    business_name: str
    fact_key: str
    signal_key: str | None = None
    kind: ProfileChangeKind
    previous_value: str | float | bool | None = None
    current_value: str | float | bool
    previous_confidence: int | None = None
    current_confidence: int
    changed_at: datetime


class ProfileChangeService:
    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.territories = TerritoryRepository(session, workspace_id=workspace_id)

    def list(
        self,
        profile_id: str,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ProfileFactChangeRead]:
        profile = self.territories.get(profile_id)
        slugs = [profile_trade_spec(key).niche_slug for key in profile.trade_keys or []]
        if not slugs:
            slugs = [profile.niche.slug]
        niche_ids = list(
            self.session.scalars(select(NicheModel.id).where(NicheModel.slug.in_(slugs)))
        )
        selected = {
            SIGNAL_FACTS[signal]: signal
            for signal in profile.signal_keys or []
            if signal in SIGNAL_FACTS
        }
        if not selected or not niche_ids:
            return []
        statement = (
            select(BusinessFactChangeModel, BusinessModel)
            .join(BusinessModel, BusinessModel.id == BusinessFactChangeModel.business_id)
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .where(
                BusinessNicheMembershipModel.niche_id.in_(niche_ids),
                BusinessFactChangeModel.fact_key.in_(selected),
                active_membership_condition(),
            )
            .order_by(BusinessFactChangeModel.changed_at.desc())
        )
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
            if exclusion in exclusions:
                statement = statement.where(or_(field.is_(False), field.is_(None)))
        if profile.latitude is not None and profile.longitude is not None:
            lat_km = (BusinessModel.latitude - profile.latitude) * 111.32
            lng_km = (
                (BusinessModel.longitude - profile.longitude)
                * 111.32
                * func.cos(func.radians(profile.latitude))
            )
            statement = statement.where(
                BusinessModel.latitude.is_not(None),
                BusinessModel.longitude.is_not(None),
                lat_km * lat_km + lng_km * lng_km
                <= float(profile.radius_km * profile.radius_km),
            )
        else:
            statement = statement.where(BusinessModel.market_key == profile.market_key)
        if since is not None:
            statement = statement.where(BusinessFactChangeModel.changed_at >= since)
        statement = statement.limit(max(1, min(limit, 500)))
        rows: list[ProfileFactChangeRead] = []
        seen: set[str] = set()
        for change, business in self.session.execute(statement):
            if change.id in seen:
                continue
            seen.add(change.id)
            signal = selected.get(change.fact_key)
            before = _matches_signal(signal, change.previous_value)
            after = _matches_signal(signal, change.current_value)
            kind = (
                ProfileChangeKind.ENTERED
                if after and not before
                else ProfileChangeKind.EXITED
                if before and not after
                else ProfileChangeKind.UPDATED
            )
            rows.append(
                ProfileFactChangeRead(
                    id=change.id,
                    business_id=business.id,
                    business_name=business.display_name,
                    fact_key=change.fact_key,
                    signal_key=signal,
                    kind=kind,
                    previous_value=change.previous_value,
                    current_value=change.current_value,
                    previous_confidence=change.previous_confidence,
                    current_confidence=change.current_confidence,
                    changed_at=change.changed_at,
                )
            )
        return rows


def _matches_signal(signal: str | None, value) -> bool:
    if signal == "website_unavailable":
        return value in {"missing", "unavailable", "parked"}
    if signal in {"no_quote_flow", "no_contact_form"}:
        return value is False
    if signal == "reviews_under_15":
        return isinstance(value, (int, float)) and value < 15
    return False
