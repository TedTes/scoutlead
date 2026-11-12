from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from audience_runs.scheduler import enqueue_waiting_audience_runs
from db.models import (
    AudienceRunModel,
    BusinessIndexSegmentModel,
    CoverageRequestModel,
    QueueJobModel,
)
from db.session import create_database
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from shared.utils import utcnow


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _waiting_run_with_processing_city(session) -> AudienceRunModel:
    run = AudienceRunModel(
        id="audience_run_1",
        workspace_id=None,
        audience_id="audience_1",
        criteria_version=1,
        state="waiting_validation",
        requested_count=25,
        result_count=0,
        new_result_count=0,
        deadline_at=utcnow() - timedelta(minutes=1),
    )
    session.add_all(
        [
            run,
            CoverageRequestModel(
                id="coverage_1",
                run_id=run.id,
                audience_id=run.audience_id,
                niche_id="niche_1",
                market_key="toronto ontario canada",
                requested_count=25,
                status="processing",
            ),
            BusinessIndexSegmentModel(
                id="segment_1",
                niche_id="niche_1",
                market_key="toronto ontario canada",
                market_label="Toronto, Ontario, Canada",
                status="active",
                demand_count=1,
                target_business_count=25,
                source_plan=[],
                source_state={},
            ),
        ]
    )
    session.commit()
    return run


def test_waiting_run_does_not_starve_its_active_city_pipeline() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        run = _waiting_run_with_processing_city(session)
        QueueService(session).enqueue_business_index_refresh(
            segment_id="segment_1"
        )

        enqueued = enqueue_waiting_audience_runs(session)

        assert enqueued == 0
        audience_jobs = list(
            session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.type == JobType.AUDIENCE_RUN.value,
                    QueueJobModel.status == JobStatus.QUEUED.value,
                )
            )
        )
        assert audience_jobs == []
        assert session.get(AudienceRunModel, run.id).state == "waiting_validation"


def test_waiting_run_resumes_after_active_city_pipeline_finishes() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        run = _waiting_run_with_processing_city(session)
        pipeline_job = QueueService(session).enqueue_business_index_refresh(
            segment_id="segment_1"
        )
        pipeline_job.status = JobStatus.COMPLETED.value
        pipeline_job.completed_at = utcnow()
        session.commit()

        enqueued = enqueue_waiting_audience_runs(session)

        assert enqueued == 1
        audience_job = session.scalar(
            select(QueueJobModel).where(
                QueueJobModel.type == JobType.AUDIENCE_RUN.value,
                QueueJobModel.status == JobStatus.QUEUED.value,
            )
        )
        assert audience_job is not None
        assert audience_job.payload["audience_run_id"] == run.id
