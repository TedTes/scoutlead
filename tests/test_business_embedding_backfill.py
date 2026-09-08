from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import BusinessModel
from db.session import create_database
from seeding.embedding_backfill import BusinessEmbeddingBackfillService
from seeding.service import BusinessSeedService
from tests.test_business_seeding import painting_seed


class FakeBatchEmbeddingClient:
    model = "fake-batch-embedding"
    dimension = 3

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        self.calls.append(texts)
        return [[float(index), float(len(text)), 1.0] for index, text in enumerate(texts, start=1)]


def test_business_embedding_backfill_embeds_missing_businesses() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds([painting_seed()], batch_id="painting-toronto-v1")
        business = session.scalar(select(BusinessModel))
        assert business is not None
        assert business.embedding is None

        client = FakeBatchEmbeddingClient()
        summary = BusinessEmbeddingBackfillService(session, embedding_client=client).backfill()

        assert summary.scanned == 1
        assert summary.eligible == 1
        assert summary.embedded == 1
        assert summary.skipped == 0
        assert summary.failed_batches == 0
        assert business.embedding == [1.0, float(len(client.calls[0][0])), 1.0]
        assert business.embedding_model == "fake-batch-embedding"
        assert business.embedding_updated_at is not None


def test_business_embedding_backfill_skips_current_model_without_force() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds([painting_seed()], batch_id="painting-toronto-v1")
        client = FakeBatchEmbeddingClient()
        service = BusinessEmbeddingBackfillService(session, embedding_client=client)
        service.backfill()
        first_call_count = len(client.calls)

        summary = service.backfill()

        assert summary.eligible == 0
        assert summary.embedded == 0
        assert len(client.calls) == first_call_count


def test_business_embedding_backfill_force_rebuilds_current_model() -> None:
    session_factory = _session_factory()

    with session_factory() as session:
        BusinessSeedService(session).import_seeds([painting_seed()], batch_id="painting-toronto-v1")
        client = FakeBatchEmbeddingClient()
        service = BusinessEmbeddingBackfillService(session, embedding_client=client)
        service.backfill()

        summary = service.backfill(force=True)

        assert summary.eligible == 1
        assert summary.embedded == 1
        assert len(client.calls) == 2


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
