from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    BusinessFactModel,
    BusinessIndexSegmentModel,
    BusinessPublicationModel,
)
from job_queue.service import QueueService
from pipeline_outbox.repository import PipelineOutboxRepository
from shared.utils import utcnow


def expire_stale_evidence(session: Session) -> dict[str, int]:
    now = utcnow()
    facts = list(
        session.scalars(
            select(BusinessFactModel).where(
                BusinessFactModel.expires_at.is_not(None),
                BusinessFactModel.expires_at < now,
                BusinessFactModel.resolution_state != "stale",
            )
        )
    )
    for fact in facts:
        fact.resolution_state = "stale"

    publications = list(
        session.scalars(
            select(BusinessPublicationModel).where(
                BusinessPublicationModel.expires_at.is_not(None),
                BusinessPublicationModel.expires_at < now,
                BusinessPublicationModel.status == "published",
            )
        )
    )
    outbox = PipelineOutboxRepository(session)
    queue = QueueService(session)
    queued_segments: set[str] = set()
    for publication in publications:
        publication.status = "stale"
        publication.reasons = [
            *(publication.reasons or []),
            {"code": "validation_expired", "expired_at": now.isoformat()},
        ]
        outbox.emit(
            topic="business.publication_changed",
            aggregate_type="business_publication",
            aggregate_id=publication.id,
            payload={
                "publication_id": publication.id,
                "business_id": publication.business_id,
                "niche_id": publication.niche_id,
                "market_key": publication.market_key,
                "status": "stale",
            },
            idempotency_key=(
                f"publication:{publication.id}:stale:{publication.expires_at}"
            ),
        )
        segment = session.scalar(
            select(BusinessIndexSegmentModel)
            .where(
                BusinessIndexSegmentModel.niche_id == publication.niche_id,
                BusinessIndexSegmentModel.market_key == publication.market_key,
            )
            .limit(1)
        )
        if segment is not None and segment.id not in queued_segments:
            queue.enqueue_business_index_refresh(
                segment_id=segment.id,
                commit=False,
            )
            queued_segments.add(segment.id)
    session.commit()
    return {
        "stale_facts": len(facts),
        "stale_publications": len(publications),
        "queued_segments": len(queued_segments),
    }
