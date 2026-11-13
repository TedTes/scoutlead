from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from audience_runs.scheduler import enqueue_waiting_audience_runs
from db.models import QueueJobModel, TerritoryModel
from db.session import create_database
from job_queue.schemas import JobStatus, JobType


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _audience(session, *, audience_id: str, state: str) -> TerritoryModel:
    audience = TerritoryModel(
        id=audience_id,
        workspace_id="workspace_1",
        product_id="product_1",
        niche_id="niche_1",
        market_key="toronto ontario canada",
        label="Electricians in Toronto",
        criteria_hash="criteria_1",
        match_state=state,
    )
    session.add(audience)
    session.commit()
    return audience


def test_scheduler_queues_current_saved_search_state() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        audience = _audience(session, audience_id="audience_1", state="queued")

        enqueued = enqueue_waiting_audience_runs(session)

        assert enqueued == 1
        job = session.scalar(
            select(QueueJobModel).where(
                QueueJobModel.type == JobType.AUDIENCE_RUN.value,
                QueueJobModel.status == JobStatus.QUEUED.value,
            )
        )
        assert job is not None
        assert job.payload["audience_run_id"] == audience.id


def test_scheduler_does_not_requeue_a_completed_saved_search() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        _audience(session, audience_id="audience_1", state="ready")

        assert enqueue_waiting_audience_runs(session) == 0
        assert session.scalar(select(QueueJobModel)) is None
