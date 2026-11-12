from sqlalchemy import select
from sqlalchemy.orm import Session

from audience_runs.schemas import AudienceRunState
from db.models import (
    AudienceRunModel,
    BusinessIndexSegmentModel,
    CoverageRequestModel,
    QueueJobModel,
)
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from shared.utils import utcnow


PIPELINE_JOB_TYPES = (
    JobType.BUSINESS_INDEX_REFRESH.value,
    JobType.SOURCE_FETCH.value,
    JobType.BUSINESS_IDENTITY_RESOLVE.value,
    JobType.BUSINESS_OPPORTUNITY_AUDIT.value,
)


def enqueue_waiting_audience_runs(session: Session, *, limit: int = 50) -> int:
    runs = list(
        session.scalars(
            select(AudienceRunModel)
            .where(
                AudienceRunModel.state == AudienceRunState.WAITING_VALIDATION.value,
            )
            .order_by(AudienceRunModel.deadline_at, AudienceRunModel.created_at)
            .limit(limit)
        )
    )
    queue = QueueService(session)
    enqueued = 0
    for run in runs:
        # Matching cannot make progress while the active city is still being
        # collected. Re-enqueuing the run every minute used to keep the
        # high-priority audience job ahead of its own refresh/source jobs,
        # starving discovery indefinitely on a single-worker deployment.
        if _processing_coverage_has_active_pipeline(session, run.id):
            continue
        queue.enqueue_audience_run(
            run.id,
            delay_seconds=0 if run.deadline_at <= utcnow() else 30,
        )
        enqueued += 1
    return enqueued


def _processing_coverage_has_active_pipeline(
    session: Session,
    run_id: str,
) -> bool:
    processing_pairs = set(
        session.execute(
            select(
                CoverageRequestModel.niche_id,
                CoverageRequestModel.market_key,
            ).where(
                CoverageRequestModel.run_id == run_id,
                CoverageRequestModel.status == "processing",
            )
        )
    )
    if not processing_pairs:
        return False

    segments = session.scalars(
        select(BusinessIndexSegmentModel).where(
            BusinessIndexSegmentModel.niche_id.in_(
                {pair[0] for pair in processing_pairs}
            ),
            BusinessIndexSegmentModel.market_key.in_(
                {pair[1] for pair in processing_pairs}
            ),
        )
    )
    segment_ids = [
        segment.id
        for segment in segments
        if (segment.niche_id, segment.market_key) in processing_pairs
    ]
    if not segment_ids:
        return False

    return (
        session.scalar(
            select(QueueJobModel.id)
            .where(
                QueueJobModel.status.in_(
                    [JobStatus.QUEUED.value, JobStatus.RUNNING.value]
                ),
                QueueJobModel.type.in_(PIPELINE_JOB_TYPES),
                QueueJobModel.payload["segment_id"]
                .as_string()
                .in_(segment_ids),
            )
            .limit(1)
        )
        is not None
    )
