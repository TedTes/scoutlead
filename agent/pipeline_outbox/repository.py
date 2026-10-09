from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import PipelineOutboxEventModel
from shared.utils import new_id, utcnow


class PipelineOutboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def emit(
        self,
        *,
        topic: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        idempotency_key: str,
    ) -> PipelineOutboxEventModel:
        existing = self.session.scalar(
            select(PipelineOutboxEventModel)
            .where(PipelineOutboxEventModel.idempotency_key == idempotency_key)
            .limit(1)
        )
        if existing is not None:
            return existing
        model = PipelineOutboxEventModel(
            id=new_id("outbox"),
            idempotency_key=idempotency_key,
            topic=topic,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            status="pending",
            attempts=0,
            available_at=utcnow(),
        )
        self.session.add(model)
        self.session.flush()
        return model

    def claim_next(self) -> PipelineOutboxEventModel | None:
        self.recover_stale_publishing()
        event = self.session.scalar(
            select(PipelineOutboxEventModel)
            .where(
                PipelineOutboxEventModel.status == "pending",
                PipelineOutboxEventModel.available_at <= utcnow(),
            )
            .order_by(PipelineOutboxEventModel.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if event is None:
            return None
        event.status = "publishing"
        event.attempts += 1
        self.session.commit()
        self.session.refresh(event)
        return event

    def recover_stale_publishing(
        self,
        *,
        stale_after_seconds: int = 300,
    ) -> int:
        cutoff = utcnow() - timedelta(seconds=stale_after_seconds)
        events = list(
            self.session.scalars(
                select(PipelineOutboxEventModel)
                .where(
                    PipelineOutboxEventModel.status == "publishing",
                    PipelineOutboxEventModel.updated_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for event in events:
            event.status = "pending"
            event.available_at = utcnow()
            event.last_error = "Publisher stopped before the event was acknowledged."
        if events:
            self.session.commit()
        return len(events)

    def published(self, event_id: str) -> None:
        event = self.session.get(PipelineOutboxEventModel, event_id)
        if event is None:
            return
        event.status = "published"
        event.published_at = utcnow()
        self.session.commit()

    def retry(self, event_id: str, error: str) -> None:
        event = self.session.get(PipelineOutboxEventModel, event_id)
        if event is None:
            return
        event.status = "pending" if event.attempts < 5 else "dead_letter"
        event.available_at = utcnow() + timedelta(seconds=30 * event.attempts)
        event.last_error = error
        self.session.commit()
