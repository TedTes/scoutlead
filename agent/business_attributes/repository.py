from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    BusinessAttributeDefinitionModel,
    BusinessAttributeModel,
)
from business_attributes.attribute_scoring import score_attribute
from business_attributes.freshness import attribute_expires_at
from shared.utils import new_id


class BusinessAttributeKey(StrEnum):
    WEBSITE_STATUS = "website_status"
    # Legacy identifiers retained only to read old snapshots and migrations.
    # Current collectors and resolvers never create these attributes.
    QUOTE_OR_BOOKING_FORM_PRESENT = "quote_or_booking_form_present"
    CONTACT_FORM_PRESENT = "contact_form_present"
    GOOGLE_RATING = "google_rating"
    GOOGLE_REVIEW_COUNT = "google_review_count"
    BUSINESS_OPERATIONAL = "business_operational"


@dataclass(frozen=True)
class BusinessAttributeValue:
    key: BusinessAttributeKey | str
    value: str | float | bool
    observed_at: datetime
    source_evidence_id: str | None = None
    confidence: int = 100
    source_provider: str | None = None
    source_external_id: str | None = None
    source_query_signature: str | None = None
    evidence_hash: str | None = None
    source_url: str | None = None
    evidence: dict[str, Any] | None = None
    expires_at: datetime | None = None


class BusinessAttributeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        business_id: str,
        fact: BusinessAttributeValue,
        *,
        commit: bool = False,
        track_change: bool = True,
    ) -> BusinessAttributeModel:
        model, _ = self.upsert_with_value_change(
            business_id,
            fact,
            commit=commit,
            track_change=track_change,
        )
        return model

    def upsert_with_value_change(
        self,
        business_id: str,
        fact: BusinessAttributeValue,
        *,
        commit: bool = False,
        track_change: bool = True,
    ) -> tuple[BusinessAttributeModel, bool]:
        attribute_key = _fact_key(fact.key)
        expires_at = fact.expires_at or attribute_expires_at(attribute_key, fact.observed_at)
        existing = self.session.scalar(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id == business_id,
                BusinessAttributeModel.attribute_key == attribute_key,
            )
        )
        if (
            existing is not None
            and _aware(existing.observed_at) > _aware(fact.observed_at)
        ):
            return existing, False
        previous_value = attribute_value(existing)
        value_changed = existing is None or previous_value != fact.value
        value_type, value_text, value_number, value_boolean = _typed_value(fact.value)
        definition = self._attribute_definition(attribute_key)
        scored = score_attribute(
            attribute_key,
            fact.value,
            opportunity_direction=(definition.opportunity_direction if definition else None),
            config=(definition.config if definition else None),
        )
        source_evidence = (
            self.session.get(BusinessAttributeModel, fact.source_evidence_id)
            if fact.source_evidence_id
            else None
        )
        source_provider = fact.source_provider or (
            source_evidence.source_provider if source_evidence else None
        )
        source_external_id = fact.source_external_id or (
            source_evidence.source_external_id if source_evidence else None
        )
        source_query_signature = fact.source_query_signature or (
            source_evidence.source_query_signature if source_evidence else None
        )
        evidence_hash = fact.evidence_hash or (
            source_evidence.evidence_hash if source_evidence else None
        )
        source_url = fact.source_url or (
            source_evidence.source_url if source_evidence else None
        )
        evidence = fact.evidence if fact.evidence is not None else (
            source_evidence.evidence if source_evidence else {}
        )
        if existing is None:
            existing = BusinessAttributeModel(
                id=new_id("business_attribute"),
                business_id=business_id,
                attribute_key=attribute_key,
                signal_definition_id=definition.id if definition else None,
                value_type=value_type,
                value_text=value_text,
                value_number=value_number,
                value_boolean=value_boolean,
                confidence=fact.confidence,
                opportunity_score=scored.score,
                score_version=scored.version,
                score_reason=scored.reason,
                observed_at=fact.observed_at,
                expires_at=expires_at,
                source_provider=source_provider,
                source_external_id=source_external_id,
                source_query_signature=source_query_signature,
                evidence_hash=evidence_hash,
                source_url=source_url,
                evidence=evidence,
            )
            self.session.add(existing)
        else:
            if existing.signal_definition_id is None:
                existing.signal_definition_id = definition.id if definition else None
            existing.value_type = value_type
            existing.value_text = value_text
            existing.value_number = value_number
            existing.value_boolean = value_boolean
            existing.confidence = fact.confidence
            existing.opportunity_score = scored.score
            existing.score_version = scored.version
            existing.score_reason = scored.reason
            existing.observed_at = fact.observed_at
            existing.expires_at = expires_at
            if source_provider is not None:
                existing.source_provider = source_provider
            if source_external_id is not None:
                existing.source_external_id = source_external_id
            if source_query_signature is not None:
                existing.source_query_signature = source_query_signature
            if evidence_hash is not None:
                existing.evidence_hash = evidence_hash
            if source_url is not None:
                existing.source_url = source_url
            if evidence:
                existing.evidence = evidence
        if commit:
            self.session.commit()
            self.session.refresh(existing)
        else:
            self.session.flush()
        return existing, value_changed

    def _attribute_definition(
        self, attribute_key: str
    ) -> BusinessAttributeDefinitionModel | None:
        return self.session.scalar(
            select(BusinessAttributeDefinitionModel)
            .where(BusinessAttributeDefinitionModel.key == attribute_key)
            .limit(1)
        )

    def map_for_businesses(
        self,
        business_ids: list[str],
    ) -> dict[str, dict[str, BusinessAttributeModel]]:
        if not business_ids:
            return {}
        rows = self.session.scalars(
            select(BusinessAttributeModel).where(
                BusinessAttributeModel.business_id.in_(business_ids),
            )
        )
        result: dict[str, dict[str, BusinessAttributeModel]] = {}
        for row in rows:
            result.setdefault(row.business_id, {})[row.attribute_key] = row
        return result


def attribute_value(fact: BusinessAttributeModel | None) -> Any:
    if fact is None:
        return None
    if fact.value_type == "boolean":
        return fact.value_boolean
    if fact.value_type == "number":
        return fact.value_number
    return fact.value_text


def _fact_key(key: BusinessAttributeKey | str) -> str:
    return key.value if isinstance(key, BusinessAttributeKey) else key


def _typed_value(value: str | float | bool) -> tuple[str, str | None, float | None, bool | None]:
    if isinstance(value, bool):
        return "boolean", None, None, value
    if isinstance(value, (int, float)):
        return "number", None, float(value), None
    return "text", str(value), None, None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
