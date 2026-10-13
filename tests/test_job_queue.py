from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.session import create_database
from job_queue.repository import QueueRepository
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
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
        claimed.locked_at = utcnow() - timedelta(hours=2)
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
        claimed.locked_at = utcnow() - timedelta(hours=2)
        session.commit()

        recovered = queue.recover_stale_running(stale_after_seconds=3600)

        assert [item.id for item in recovered] == [job.id]
        assert recovered[0].status == JobStatus.DEAD_LETTER.value
        assert recovered[0].dead_lettered_at is not None


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


def test_enqueue_once_uses_a_database_idempotency_key() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)

        first = queue.enqueue_once(
            JobType.BUSINESS_INDEX_REFRESH,
            {"segment_id": "segment_1"},
            dedupe_key="segment_1",
        )
        second = queue.enqueue_once(
            JobType.BUSINESS_INDEX_REFRESH,
            {"segment_id": "segment_1"},
            dedupe_key="segment_1",
        )

        assert second.id == first.id
        assert first.idempotency_key == "business_index.refresh:segment_1"


def test_completed_idempotent_job_can_be_enqueued_again() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        first = queue.enqueue_once(
            JobType.BUSINESS_INDEX_REFRESH,
            {"segment_id": "segment_1"},
            dedupe_key="segment_1",
        )
        queue.claim_next()
        queue.complete(first.id)

        second = queue.enqueue_once(
            JobType.BUSINESS_INDEX_REFRESH,
            {"segment_id": "segment_1"},
            dedupe_key="segment_1",
        )

        assert second.id != first.id


def test_interactive_jobs_are_claimed_before_bulk_signal_collection() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        queue.enqueue(
            JobType.SIGNAL_COLLECTION,
            {"signal_definition_id": "signal_1"},
        )
        audience = queue.enqueue(
            JobType.AUDIENCE_RUN,
            {"audience_run_id": "audience_run_1"},
        )

        claimed = queue.claim_next()

        assert claimed is not None
        assert claimed.id == audience.id


def test_pipeline_jobs_are_claimed_before_bulk_signal_collection() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        queue = QueueRepository(session)
        queue.enqueue(
            JobType.SIGNAL_COLLECTION,
            {"signal_definition_id": "signal_1"},
        )
        source_fetch = queue.enqueue(
            JobType.SOURCE_FETCH,
            {"segment_id": "segment_1", "source_index": 0},
        )

        claimed = queue.claim_next()

        assert claimed is not None
        assert claimed.id == source_fetch.id


def test_signal_collection_idempotency_key_is_bounded_for_large_batches() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business_ids = [f"business_{index:03d}_{'x' * 52}" for index in range(100)]

        first = QueueService(session).enqueue_signal_collection(
            signal_definition_id="signal_mobile_performance_score",
            signal_version=1,
            business_ids=business_ids,
            requested_by="admin",
            reason="Backfill active website signals",
            batch_number=1,
        )
        second = QueueService(session).enqueue_signal_collection(
            signal_definition_id="signal_mobile_performance_score",
            signal_version=1,
            business_ids=list(reversed(business_ids)),
            requested_by="admin",
            reason="Backfill active website signals",
            batch_number=1,
        )

        assert second.id == first.id
        assert len(first.idempotency_key or "") <= 500
        assert first.payload["business_ids"] == business_ids


def test_signal_validation_job_is_idempotent_for_a_collection_batch() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business_ids = ["business_2", "business_1"]

        first = QueueService(session).enqueue_signal_validation(
            signal_definition_id="signal_mobile_viewport_present",
            signal_version=2,
            business_ids=business_ids,
            collection_job_id="job_collection",
        )
        second = QueueService(session).enqueue_signal_validation(
            signal_definition_id="signal_mobile_viewport_present",
            signal_version=2,
            business_ids=list(reversed(business_ids)),
            collection_job_id="job_collection",
        )

        assert second.id == first.id
        assert first.type == JobType.SIGNAL_VALIDATION.value
        assert first.parent_run_id == "job_collection"


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
