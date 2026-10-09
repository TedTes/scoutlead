from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AudienceRunModel, PipelineOutboxEventModel, TerritoryModel
from job_queue.service import QueueService
from pipeline_outbox.repository import PipelineOutboxRepository


PUBLICATION_CHANGED = "business.publication_changed"


class PipelineOutboxDispatcher:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.events = PipelineOutboxRepository(session)

    def dispatch_one(self) -> bool:
        event = self.events.claim_next()
        if event is None:
            return False
        try:
            self._dispatch(event)
        except Exception as exc:
            self.events.retry(event.id, str(exc))
            raise
        self.events.published(event.id)
        return True

    def _dispatch(self, event: PipelineOutboxEventModel) -> None:
        if event.topic != PUBLICATION_CHANGED:
            raise ValueError(f"unsupported pipeline event: {event.topic}")
        if event.payload.get("status") != "published":
            return
        niche_id = str(event.payload.get("niche_id") or "")
        market_key = str(event.payload.get("market_key") or "")
        if not niche_id or not market_key:
            return
        waiting_runs = list(
            self.session.execute(
                select(AudienceRunModel, TerritoryModel)
                .join(TerritoryModel, TerritoryModel.id == AudienceRunModel.audience_id)
                .where(
                    AudienceRunModel.state == "waiting_validation",
                    TerritoryModel.market_key == market_key,
                )
            ).all()
        )
        queue = QueueService(self.session)
        for run, audience in waiting_runs:
            if audience.niche_id != niche_id and niche_id not in _profile_niche_ids(
                self.session,
                audience,
            ):
                continue
            queue.enqueue_audience_run(run.id, commit=False)
        self.session.commit()


def _profile_niche_ids(session: Session, audience: TerritoryModel) -> set[str]:
    from territories.refresh import _territory_niches

    return {niche.id for niche in _territory_niches(session, audience)}
