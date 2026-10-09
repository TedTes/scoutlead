from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.claims import FactClaim, FactClaimRepository
from business_facts.service import reconcile_business_facts
from db.models import BusinessModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session) -> BusinessModel:
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


def test_fact_claim_recording_is_idempotent() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business = _business(session)
        now = utcnow()
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="public_listing",
            content_hash="claim-test",
            raw_payload={},
            observed_at=now,
        )
        session.add(observation)
        session.commit()
        claim = FactClaim(
            business_id=business.id,
            fact_key="website_status",
            value="not_listed",
            source_observation_id=observation.id,
            confidence=55,
            extractor="test",
            extractor_version=1,
            observed_at=now,
            expires_at=now + timedelta(days=30),
        )
        repository = FactClaimRepository(session)

        first = repository.record(claim, commit=True)
        second = repository.record(claim, commit=True)

        assert second.id == first.id
        assert session.query(type(first)).count() == 1


def test_reconciliation_records_claim_provenance() -> None:
    session_factory = _session_factory()
    with session_factory() as session:
        business = _business(session)
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="google_places",
            content_hash="reconcile-test",
            raw_payload={
                "website_presence_status": "no_website_listed",
                "userRatingCount": 8,
            },
            observed_at=utcnow(),
        )
        session.add(observation)
        session.commit()

        resolved = reconcile_business_facts(session, business.id)
        session.commit()

        assert resolved["website_status"] == "not_listed"
        website_fact = next(
            fact for fact in business.facts if fact.fact_key == "website_status"
        )
        assert website_fact.resolution_state == "probable"
        assert len(website_fact.supporting_claim_ids) == 1
