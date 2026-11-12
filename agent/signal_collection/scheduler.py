from __future__ import annotations

from sqlalchemy import and_, or_, select, true
from sqlalchemy.orm import Session, aliased

from business_index.eligibility import searchable_business_conditions
from db.models import (
    BusinessAttributeModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    SignalDefinitionModel,
)
from job_queue.service import QueueService
from seeding.batches import active_membership_condition
from shared.utils import utcnow
from signal_collection.requirements import (
    STANDING_WEBSITE_ATTRIBUTE_KEYS,
    fact_requires_collection,
)


def enqueue_due_signal_collections(
    session: Session,
    *,
    limit: int = 50,
    batch_size: int = 10,
) -> int:
    """Queue a bounded standing refresh of missing or stale website evidence."""

    if limit <= 0:
        return 0
    now = utcnow()
    fact = aliased(BusinessAttributeModel, name="scheduled_attribute_fact")
    statement = (
        select(
            SignalDefinitionModel,
            BusinessModel.id,
        )
        .select_from(SignalDefinitionModel)
        .join(BusinessModel, true())
        .join(
            BusinessNicheMembershipModel,
            BusinessNicheMembershipModel.business_id == BusinessModel.id,
        )
        .outerjoin(
            fact,
            and_(
                fact.signal_definition_id == SignalDefinitionModel.id,
                fact.business_id == BusinessModel.id,
            ),
        )
        .where(
            SignalDefinitionModel.key.in_(STANDING_WEBSITE_ATTRIBUTE_KEYS),
            SignalDefinitionModel.status == "active",
            SignalDefinitionModel.collector_key.is_not(None),
            SignalDefinitionModel.opportunity_direction != "none",
            fact_requires_collection(fact, now=now),
            active_membership_condition(),
            *searchable_business_conditions(now=now),
            # Website/PageSpeed collectors cannot inspect an unknown URL.
            or_(
                ~SignalDefinitionModel.collector_key.in_(
                    ("website_http", "website_dom", "pagespeed_mobile")
                ),
                BusinessModel.website_url.is_not(None),
            ),
        )
        .order_by(
            fact.expires_at.asc().nullsfirst(),
            fact.observed_at.asc().nullsfirst(),
            BusinessModel.id,
            SignalDefinitionModel.id,
        )
        .limit(limit)
    )
    rows = session.execute(statement).unique().all()
    grouped: dict[str, tuple[SignalDefinitionModel, list[str]]] = {}
    for definition, business_id in rows:
        _, business_ids = grouped.setdefault(definition.id, (definition, []))
        if business_id not in business_ids:
            business_ids.append(str(business_id))

    queue = QueueService(session)
    queued = 0
    for definition, business_ids in grouped.values():
        chunks = [
            business_ids[index : index + max(1, batch_size)]
            for index in range(0, len(business_ids), max(1, batch_size))
        ]
        for batch_number, chunk in enumerate(chunks, start=1):
            queue.enqueue_signal_collection(
                signal_definition_id=definition.id,
                signal_version=definition.version,
                business_ids=chunk,
                requested_by=None,
                reason="scheduled_website_evidence_refresh",
                batch_number=batch_number,
                commit=False,
            )
            queued += len(chunk)
    if queued:
        session.commit()
    return queued
