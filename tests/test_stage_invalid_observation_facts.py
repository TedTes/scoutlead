from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.repository import BusinessFactRepository, BusinessFactValue
from canonical.repository import CanonicalRepository
from db.models import BusinessFactModel, SourceObservationModel, ValidationResultModel
from db.session import create_database
from scripts.stage_invalid_observation_facts import stage_invalid_facts
from shared.utils import utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _published_fact(session):
    link = CanonicalRepository(session).upsert_from_discovery_result(
        company_name="Example Services",
        geography="Toronto, ON",
        source="google_places",
        raw={"id": "place_1", "rating": 4.8},
    )
    observation = session.get(SourceObservationModel, link.source_observation_id)
    assert observation is not None
    fact = BusinessFactRepository(session).upsert(
        link.business_id,
        BusinessFactValue(
            key="google_rating",
            value=4.8,
            observed_at=utcnow(),
            source_observation_id=observation.id,
            quality_state="published",
        ),
    )
    session.commit()
    observation.raw_payload = {**observation.raw_payload, "changed": True}
    session.commit()
    return fact


def test_stage_invalid_facts_is_read_only_by_default() -> None:
    with _session_factory()() as session:
        fact = _published_fact(session)

        report = stage_invalid_facts(session)

        session.refresh(fact)
        assert report["affected_fact_count"] == 1
        assert report["database_mutated"] is False
        assert fact.quality_state == "published"


def test_stage_invalid_facts_requires_explicit_apply() -> None:
    with _session_factory()() as session:
        fact = _published_fact(session)

        report = stage_invalid_facts(session, apply=True)

        session.refresh(fact)
        assert report["affected_fact_count"] == 1
        assert report["database_mutated"] is True
        assert fact.quality_state == "staged"
        assert session.query(ValidationResultModel).count() == 1
