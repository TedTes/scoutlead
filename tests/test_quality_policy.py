from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import BusinessFactModel, BusinessModel, QualityMetricSnapshotModel
from db.session import create_database
from quality.fact_policy import FactQualityPolicyService
from quality.repository import QualityRepository, QualityScope
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session):
    now = utcnow()
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
    session.add(business)
    session.commit()
    return business


def test_quality_metric_uses_wilson_lower_bound() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business = _business(session)
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
        business = _business(session)
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
