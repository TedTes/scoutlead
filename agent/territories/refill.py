from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.models import AudienceResultModel, AudienceRunModel, TerritoryModel
from job_queue.service import QueueService


def enqueue_refill_if_depleted(
    session: Session,
    territory_id: str | None,
) -> bool:
    if not territory_id:
        return False
    territory = session.get(TerritoryModel, territory_id)
    if (
        territory is None
        or territory.status != "active"
        or territory.refill_policy != "when_depleted"
    ):
        return False
    latest_run = session.scalar(
        select(AudienceRunModel)
        .where(
            AudienceRunModel.audience_id == territory.id,
            AudienceRunModel.state.in_(("ready", "partial")),
        )
        .order_by(AudienceRunModel.created_at.desc())
        .limit(1)
    )
    if latest_run is None:
        return False
    remaining = session.scalar(
        select(func.count())
        .select_from(AudienceResultModel)
        .where(
            AudienceResultModel.run_id == latest_run.id,
            AudienceResultModel.shortlisted_at.is_(None),
            AudienceResultModel.contacted_at.is_(None),
            or_(
                AudienceResultModel.review_status.is_(None),
                AudienceResultModel.review_status != "not_fit",
            ),
        )
    ) or 0
    threshold = max(1, min(5, territory.batch_size // 5))
    if remaining > threshold:
        return False
    # Import locally because audience result updates invoke this check.
    from audience_runs.service import AudienceRunService

    run = AudienceRunService(
        session,
        workspace_id=territory.workspace_id,
    ).create(territory.id, commit=False)
    QueueService(session).enqueue_audience_run(run.id, commit=False)
    session.commit()
    return True
