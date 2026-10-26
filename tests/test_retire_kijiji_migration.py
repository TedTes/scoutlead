from datetime import timedelta
from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db.models import (
    BusinessFactModel,
    BusinessModel,
    FactClaimModel,
    SourceObservationModel,
)
from db.session import create_database
from shared.utils import utcnow


def test_kijiji_cleanup_archives_source_only_business_and_removes_observation() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    now = utcnow()
    with Session(engine) as session:
        session.add(
            BusinessModel(
                id="business_kijiji_only",
                display_name="Marketplace Painter",
                normalized_name="marketplace painter",
                website_url="https://www.kijiji.ca/v-services/example/123",
                domain="kijiji.ca",
                customer_kind="unknown",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.add(
            SourceObservationModel(
                id="sourceobs_kijiji",
                business_id="business_kijiji_only",
                source="kijiji",
                external_id="listing-123",
                content_hash="hash-kijiji",
                source_url="https://www.kijiji.ca/v-services/example/123",
                raw_payload={"title": "Marketplace Painter"},
                observed_at=now,
            )
        )
        session.commit()

    _run_migration(engine)

    with Session(engine) as session:
        business = session.get(BusinessModel, "business_kijiji_only")
        observations = list(session.scalars(select(SourceObservationModel)))

        assert business is not None
        assert business.status == "archived"
        assert business.website_url is None
        assert business.domain is None
        assert observations == []


def test_kijiji_cleanup_preserves_independently_sourced_fact_quality() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    now = utcnow()
    expires_at = now + timedelta(days=30)
    with Session(engine) as session:
        session.add(
            BusinessModel(
                id="business_mixed_sources",
                display_name="Independent Painter",
                normalized_name="independent painter",
                customer_kind="unknown",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.add_all(
            [
                SourceObservationModel(
                    id="sourceobs_kijiji_mixed",
                    business_id="business_mixed_sources",
                    source="kijiji",
                    external_id="listing-456",
                    content_hash="hash-kijiji-mixed",
                    raw_payload={"rating": 4.8},
                    observed_at=now,
                ),
                SourceObservationModel(
                    id="sourceobs_google_mixed",
                    business_id="business_mixed_sources",
                    source="google_places",
                    external_id="places/independent-painter",
                    content_hash="hash-google-mixed",
                    raw_payload={"rating": 4.8},
                    observed_at=now,
                ),
            ]
        )
        session.flush()
        session.add(
            FactClaimModel(
                id="claim_kijiji_rating",
                idempotency_key="claim:kijiji:rating",
                business_id="business_mixed_sources",
                fact_key="google_rating",
                value=4.8,
                source_observation_id="sourceobs_kijiji_mixed",
                confidence=80,
                extractor="test",
                extractor_version=1,
                observed_at=now,
                expires_at=expires_at,
            )
        )
        session.add(
            BusinessFactModel(
                id="fact_google_rating",
                business_id="business_mixed_sources",
                fact_key="google_rating",
                value_type="number",
                value_number=4.8,
                confidence=95,
                resolution_state="confirmed",
                supporting_claim_ids=["claim_kijiji_rating"],
                quality_state="published",
                quality_policy_version=1,
                observed_at=now,
                expires_at=expires_at,
                source_observation_id="sourceobs_google_mixed",
                resolver_version=3,
            )
        )
        session.commit()

    _run_migration(engine)

    with Session(engine) as session:
        business = session.get(BusinessModel, "business_mixed_sources")
        fact = session.get(BusinessFactModel, "fact_google_rating")
        observations = list(
            session.scalars(
                select(SourceObservationModel).where(
                    SourceObservationModel.business_id == "business_mixed_sources"
                )
            )
        )

        assert business is not None
        assert business.status == "active"
        assert fact is not None
        assert fact.quality_state == "published"
        assert fact.confidence == 95
        assert fact.supporting_claim_ids == []
        assert [observation.source for observation in observations] == ["google_places"]


def _run_migration(engine) -> None:
    migration = import_module(
        "db.migrations.versions.20261026_0063_retire_kijiji_source"
    )
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
