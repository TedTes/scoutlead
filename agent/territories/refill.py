from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db.models import AudienceResultModel, LeadModel, TerritoryModel
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
    if territory.match_state not in {"ready", "partial"}:
        return False
    remaining = session.scalar(
        select(func.count())
        .select_from(AudienceResultModel)
        .outerjoin(LeadModel, LeadModel.id == AudienceResultModel.outreach_lead_id)
        .where(
            AudienceResultModel.audience_id == territory.id,
            LeadModel.shortlisted_at.is_(None),
            LeadModel.last_contacted_at.is_(None),
            or_(
                LeadModel.review_status.is_(None),
                LeadModel.review_status != "not_fit",
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
