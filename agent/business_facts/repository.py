from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import BusinessFactChangeModel, BusinessFactModel
from shared.utils import new_id


class BusinessFactKey(StrEnum):
    WEBSITE_STATUS = "website_status"
    QUOTE_OR_BOOKING_FORM_PRESENT = "quote_or_booking_form_present"
    CONTACT_FORM_PRESENT = "contact_form_present"
    GOOGLE_RATING = "google_rating"
    GOOGLE_REVIEW_COUNT = "google_review_count"
    BUSINESS_OPERATIONAL = "business_operational"


@dataclass(frozen=True)
class BusinessFactValue:
    key: BusinessFactKey
    value: str | float | bool
    observed_at: datetime
    source_observation_id: str | None
    confidence: int = 100
    expires_at: datetime | None = None
    resolver_version: int = 1


class BusinessFactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        business_id: str,
        fact: BusinessFactValue,
        *,
        commit: bool = False,
    ) -> BusinessFactModel:
        model, _ = self.upsert_with_value_change(
            business_id,
            fact,
            commit=commit,
        )
        return model

    def upsert_with_value_change(
        self,
        business_id: str,
        fact: BusinessFactValue,
        *,
        commit: bool = False,
    ) -> tuple[BusinessFactModel, bool]:
        existing = self.session.scalar(
            select(BusinessFactModel).where(
                BusinessFactModel.business_id == business_id,
                BusinessFactModel.fact_key == fact.key.value,
            )
        )
        if (
            existing is not None
            and _aware(existing.observed_at) > _aware(fact.observed_at)
            and existing.resolver_version >= fact.resolver_version
        ):
            return existing, False
        previous_value = fact_value(existing)
        previous_confidence = existing.confidence if existing is not None else None
        value_changed = existing is None or previous_value != fact.value
        value_type, value_text, value_number, value_boolean = _typed_value(fact.value)
        if existing is None:
            existing = BusinessFactModel(
                id=new_id("business_fact"),
                business_id=business_id,
                fact_key=fact.key.value,
                value_type=value_type,
                value_text=value_text,
                value_number=value_number,
                value_boolean=value_boolean,
                confidence=fact.confidence,
                observed_at=fact.observed_at,
                expires_at=fact.expires_at,
                source_observation_id=fact.source_observation_id,
                resolver_version=fact.resolver_version,
            )
            self.session.add(existing)
        else:
            existing.value_type = value_type
            existing.value_text = value_text
            existing.value_number = value_number
            existing.value_boolean = value_boolean
            existing.confidence = fact.confidence
            existing.observed_at = fact.observed_at
            existing.expires_at = fact.expires_at
            existing.source_observation_id = fact.source_observation_id
            existing.resolver_version = fact.resolver_version
        if value_changed:
            self.session.add(
                BusinessFactChangeModel(
                    id=new_id("fact_change"),
                    business_id=business_id,
                    fact_key=fact.key.value,
                    previous_value=previous_value,
                    current_value=fact.value,
                    previous_confidence=previous_confidence,
                    current_confidence=fact.confidence,
                    source_observation_id=fact.source_observation_id,
                    changed_at=fact.observed_at,
                )
            )
        if commit:
            self.session.commit()
            self.session.refresh(existing)
        else:
            self.session.flush()
        return existing, value_changed

    def map_for_businesses(
        self,
        business_ids: list[str],
    ) -> dict[str, dict[str, BusinessFactModel]]:
        if not business_ids:
            return {}
        rows = self.session.scalars(
            select(BusinessFactModel).where(BusinessFactModel.business_id.in_(business_ids))
        )
        result: dict[str, dict[str, BusinessFactModel]] = {}
        for row in rows:
            result.setdefault(row.business_id, {})[row.fact_key] = row
        return result


def fact_value(fact: BusinessFactModel | None) -> Any:
    if fact is None:
        return None
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _typed_value(value: str | float | bool) -> tuple[str, str | None, float | None, bool | None]:
    if isinstance(value, bool):
        return "boolean", None, None, value
    if isinstance(value, (int, float)):
        return "number", None, float(value), None
    return "text", str(value), None, None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
