from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import create_database
from job_queue.repository import QueueRepository
from job_queue.schemas import JobStatus, JobType
from job_queue.worker import _consolidate_legacy_search_evaluations
from shared.utils import utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_recover_stale_running_requeues_interrupted_job() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        job = queue.enqueue(JobType.BUSINESS_INDEX_REFRESH, {"segment_id": "segment_1"})
        claimed = queue.claim_next()
        assert claimed is not None
        claimed.updated_at = utcnow() - timedelta(hours=2)
        session.commit()

        recovered = queue.recover_stale_running(stale_after_seconds=3600)

        assert [item.id for item in recovered] == [job.id]
        assert recovered[0].status == JobStatus.QUEUED.value
        assert recovered[0].last_error == "Worker stopped before the job completed."


def test_recover_stale_running_fails_exhausted_job() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        job = queue.enqueue(
            JobType.BUSINESS_INDEX_REFRESH,
            {"segment_id": "segment_1"},
            max_attempts=1,
        )
        claimed = queue.claim_next()
        assert claimed is not None
        claimed.updated_at = utcnow() - timedelta(hours=2)
        session.commit()

        recovered = queue.recover_stale_running(stale_after_seconds=3600)

        assert [item.id for item in recovered] == [job.id]
        assert recovered[0].status == JobStatus.FAILED.value


def test_recover_stale_running_leaves_recent_job_alone() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        queue.enqueue(JobType.BUSINESS_INDEX_REFRESH, {"segment_id": "segment_1"})
        claimed = queue.claim_next()
        assert claimed is not None

        recovered = queue.recover_stale_running(stale_after_seconds=3600)

        assert recovered == []
        assert claimed.status == JobStatus.RUNNING.value


def test_legacy_search_evaluation_jobs_are_consolidated_into_one_batch() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        payload = {
            "campaign_id": "campaign_1",
            "contract_hash": "contract_1",
            "contract": {"version": 2, "semantic_all_of": ["Independent business"]},
            "evidence_fresh_after": "2026-09-01T00:00:00+00:00",
        }
        for index in range(3):
            queue.enqueue(
                JobType.BUSINESS_SEARCH_EVALUATE,
                {**payload, "business_id": f"business_{index}"},
            )
        current = queue.claim_next()
        assert current is not None

        _consolidate_legacy_search_evaluations(session, current)

        jobs = session.query(type(current)).all()
        batch = next(job for job in jobs if job.type == JobType.BUSINESS_SEARCH_EVALUATE_BATCH)
        siblings = [
            job
            for job in jobs
            if job.type == JobType.BUSINESS_SEARCH_EVALUATE and job.id != current.id
        ]
        assert batch.payload["business_ids"] == ["business_0", "business_1", "business_2"]
        assert all(job.status == JobStatus.COMPLETED for job in siblings)
