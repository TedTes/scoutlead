from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.operational import assess_business_operational
from db.models import BusinessModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow


def _assessment(status: str):
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        now = utcnow()
        business = BusinessModel(
            id=new_id("business"),
            display_name="Mobile Painter",
            normalized_name="mobile painter",
            market_key="toronto",
            status="active",
            first_seen_at=now,
            last_seen_at=now,
        )
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="google_places",
            external_id="places/mobile-painter",
            query_signature=None,
            content_hash="b" * 64,
            source_url="https://maps.example/mobile-painter",
            raw_payload={"businessStatus": status},
            observed_at=now,
        )
        session.add_all([business, observation])
        session.commit()
        return assess_business_operational(
            session,
            business=business,
            observation=observation,
        )


def test_operational_provider_status_is_positive_evidence() -> None:
    assessment = _assessment("OPERATIONAL")

    assert assessment.value is True
    assert assessment.confidence == 100


def test_permanent_closure_is_negative_evidence() -> None:
    assessment = _assessment("CLOSED_PERMANENTLY")

    assert assessment.value is False
    assert assessment.confidence == 100


def test_temporary_closure_remains_unknown() -> None:
    assessment = _assessment("CLOSED_TEMPORARILY")

    assert assessment is None
