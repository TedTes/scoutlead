from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_attributes.operational import assess_business_operational
from business_attributes.source_payloads import source_payload_attribute_key
from db.models import BusinessAttributeModel, BusinessModel
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
        observation = BusinessAttributeModel(
            id=new_id("observation"),
            business_id=business.id,
            attribute_key=source_payload_attribute_key("google_places"),
            value_type="json",
            value_json={"businessStatus": status},
            confidence=100,
            source="google_places",
            source_external_id="places/mobile-painter",
            source_query_signature=None,
            evidence_hash="b" * 64,
            source_url="https://maps.example/mobile-painter",
            evidence={"businessStatus": status},
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
