from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    BusinessFactModel,
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessPublicationModel,
    NicheModel,
    PipelineOutboxEventModel,
    ProductModel,
    QualityMetricSnapshotModel,
    QueueJobModel,
)
from db.session import create_database
from publication.policy import PublicationPolicyService, REQUIRED_VALIDATIONS
from publication.maintenance import expire_stale_evidence
from pipeline_outbox.repository import PipelineOutboxRepository
from publication.repository import ValidationRepository, ValidationResult
from quality.repository import QualityRepository, QualityScope
from quality.fact_policy import FactQualityPolicyService
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _scope(session):
    now = utcnow()
    product = ProductModel(
        id=new_id("product"),
        product_name="Local growth",
        target_customer="Home-service businesses",
        target_geography="Toronto",
        qualification_criteria=[],
        preferred_discovery_sources=[],
        constraints=[],
    )
    niche = NicheModel(
        id=new_id("niche"),
        slug="home_service_painting",
        label="Painting contractors",
        category="painting contractors",
        default_query="painting contractors Toronto",
        active=True,
    )
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example Painting",
        normalized_name="example painting",
        geography="Toronto",
        market_key="toronto",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add_all([product, niche, business])
    session.commit()
    return business, niche


def _validations(session, business_id: str) -> None:
    now = utcnow()
    repository = ValidationRepository(session)
    for dimension, confidence in REQUIRED_VALIDATIONS.items():
        repository.record(
            ValidationResult(
                business_id=business_id,
                source_item_id=None,
                source_observation_id=None,
                validation_type=dimension,
                status="passed",
                confidence=confidence,
                reason="Test validation passed.",
                evidence=[],
                validator="test",
                validator_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
    session.commit()


def _quality_metrics(session) -> None:
    now = utcnow()
    for dimension in REQUIRED_VALIDATIONS:
        session.add(
            QualityMetricSnapshotModel(
                id=new_id("quality_metric"),
                dimension=dimension,
                sample_size=50,
                true_positive=50,
                false_positive=0,
                false_negative=0,
                true_negative=0,
                precision=1.0,
                recall=1.0,
                precision_lower_bound=0.9286,
                calculated_at=now,
            )
        )
    session.commit()


def test_publication_remains_staged_without_quality_measurement() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business, niche = _scope(session)
        _validations(session, business.id)

        publication = PublicationPolicyService(session).evaluate(
            business_id=business.id,
            niche_id=niche.id,
            market_key="toronto",
            source=None,
        )

        assert publication.status == "staged"
        assert {reason["code"] for reason in publication.reasons} == {
            "quality_sample_insufficient"
        }


def test_publication_passes_validations_and_measured_quality() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business, niche = _scope(session)
        _validations(session, business.id)
        _quality_metrics(session)

        publication = PublicationPolicyService(session).evaluate(
            business_id=business.id,
            niche_id=niche.id,
            market_key="toronto",
            source=None,
        )

        assert publication.status == "published"
        assert publication.reasons == [{"code": "policy_passed", "policy_version": 1}]
        event = session.query(PipelineOutboxEventModel).one()
        assert event.topic == "business.publication_changed"
        assert event.payload["status"] == "published"

        PublicationPolicyService(session).evaluate(
            business_id=business.id,
            niche_id=niche.id,
            market_key="toronto",
            source=None,
        )
        assert session.query(PipelineOutboxEventModel).count() == 1


def test_quality_metric_uses_wilson_lower_bound() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business, _ = _scope(session)
        quality = QualityRepository(session)
        scope = QualityScope(dimension="identity")
        for index in range(30):
            quality.add_label(
                business_id=business.id,
                scope=scope,
                expected=True,
                predicted=index != 0,
                reviewer="reviewer@example.com",
                reviewed_at=utcnow(),
            )

        metric = quality.calculate(scope)

        assert metric.sample_size == 30
        assert metric.precision == 1.0
        assert metric.recall == 29 / 30
        assert metric.precision_lower_bound is not None
        assert metric.precision_lower_bound < metric.precision


def test_opportunity_fact_stays_staged_until_its_accuracy_is_measured() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business, _ = _scope(session)
        fact = BusinessFactModel(
            id=new_id("fact"),
            business_id=business.id,
            fact_key="website_status",
            value_type="text",
            value_text="missing",
            confidence=95,
            resolution_state="confirmed",
            supporting_claim_ids=[],
            quality_state="staged",
            quality_policy_version=1,
            observed_at=utcnow(),
            resolver_version=1,
        )
        session.add(fact)
        session.commit()

        FactQualityPolicyService(session).evaluate(fact)
        assert fact.quality_state == "staged"

        session.add(
            QualityMetricSnapshotModel(
                id=new_id("quality_metric"),
                dimension="website_unavailable",
                sample_size=50,
                true_positive=50,
                false_positive=0,
                false_negative=0,
                true_negative=0,
                precision=1.0,
                recall=1.0,
                precision_lower_bound=0.9286,
                calculated_at=utcnow(),
            )
        )
        session.commit()

        FactQualityPolicyService(session).evaluate(fact)
        assert fact.quality_state == "published"


def test_expired_evidence_is_removed_from_publication_and_refresh_is_queued() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business, niche = _scope(session)
        product = session.query(ProductModel).one()
        expired_at = utcnow() - timedelta(minutes=1)
        fact = BusinessFactModel(
            id=new_id("fact"),
            business_id=business.id,
            fact_key="website_status",
            value_type="text",
            value_text="missing",
            confidence=95,
            resolution_state="confirmed",
            supporting_claim_ids=[],
            quality_state="published",
            quality_policy_version=1,
            observed_at=expired_at - timedelta(days=30),
            expires_at=expired_at,
            resolver_version=1,
        )
        publication = BusinessPublicationModel(
            id=new_id("publication"),
            business_id=business.id,
            niche_id=niche.id,
            market_key="toronto",
            status="published",
            policy_version=1,
            reasons=[{"code": "policy_passed"}],
            evaluated_at=expired_at - timedelta(days=30),
            expires_at=expired_at,
        )
        segment = BusinessIndexSegmentModel(
            id=new_id("segment"),
            niche_id=niche.id,
            product_id=product.id,
            market_key="toronto",
            market_label="Toronto",
            target_business_count=25,
            source_plan=[],
            source_state={},
        )
        session.add_all([fact, publication, segment])
        session.commit()

        result = expire_stale_evidence(session)

        assert result == {
            "stale_facts": 1,
            "stale_publications": 1,
            "queued_segments": 1,
        }
        assert fact.resolution_state == "stale"
        assert publication.status == "stale"
        job = session.query(QueueJobModel).one()
        assert job.payload["segment_id"] == segment.id


def test_stale_publishing_event_is_recovered_before_the_next_claim() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        repository = PipelineOutboxRepository(session)
        event = repository.emit(
            topic="business.publication_changed",
            aggregate_type="business_publication",
            aggregate_id="publication:test",
            payload={"status": "published"},
            idempotency_key="publication:test:recovery",
        )
        session.commit()
        event.status = "publishing"
        event.updated_at = utcnow() - timedelta(minutes=10)
        session.commit()

        claimed = repository.claim_next()

        assert claimed is not None
        assert claimed.id == event.id
        assert claimed.status == "publishing"
        assert claimed.attempts == 1
        assert claimed.last_error == (
            "Publisher stopped before the event was acknowledged."
        )
