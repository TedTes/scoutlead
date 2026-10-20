from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import BusinessFactModel, BusinessModel
from db.session import create_database
from quality.fact_policy import FactQualityPolicyService
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


def test_opportunity_fact_stays_staged_until_explicit_validation() -> None:
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
