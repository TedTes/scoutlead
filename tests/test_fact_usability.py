from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from canonical.normalization import stable_content_hash
from db.models import (
    BusinessFactModel,
    BusinessModel,
    SignalDefinitionModel,
    SourceObservationModel,
)
from db.session import create_database
from quality.fact_usability import clean_canonical_facts
from business_facts.attribute_scoring import score_attribute
from shared.utils import new_id, utcnow


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_cleanup_publishes_useful_and_deletes_only_canonical_unusable_rows() -> None:
    factory = _session_factory()
    with factory() as session:
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
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="contact_form_present",
            label="Contact form present",
            value_type="boolean",
            category="lead_capture",
            status="active",
            collector_key="website_dom",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"auto_publish": True, "requires_validation": False},
            version=1,
        )
        payload = {"place_id": "place-1", "contact_form_present": False}
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="company_website_signal",
            external_id="place-1",
            query_signature=None,
            content_hash=stable_content_hash(payload),
            source_url="https://places.example/place-1",
            raw_payload=payload,
            observed_at=now,
        )
        useful = BusinessFactModel(
            id=new_id("fact"),
            business_id=business.id,
            fact_key=definition.key,
            signal_definition_id=definition.id,
            value_type="boolean",
            value_boolean=False,
            confidence=85,
            attribute_score=0,
            score_version=1,
            score_reason="boolean state",
            resolution_state="confirmed",
            supporting_claim_ids=[],
            quality_state="staged",
            quality_policy_version=1,
            observed_at=now,
            expires_at=now + timedelta(days=30),
            source_observation_id=observation.id,
            resolver_version=1,
        )
        session.add_all([business, definition, observation, useful])
        session.commit()

        dry_run = clean_canonical_facts(session)
        assert dry_run.published == 1
        assert dry_run.deleted == 0
        assert useful.quality_state == "staged"

        applied = clean_canonical_facts(session, apply=True)
        assert applied.published == 1
        assert applied.deleted == 0
        assert useful.quality_state == "published"

        useful.expires_at = now - timedelta(seconds=1)
        session.commit()
        removed = clean_canonical_facts(session, apply=True)
        assert removed.deleted == 1
        assert removed.reasons["stale"] == 1
        assert session.scalar(select(func.count(BusinessFactModel.id))) == 0
        assert session.get(SourceObservationModel, observation.id) is not None


def test_cleanup_deletes_rejected_fact_even_when_evidence_is_intact() -> None:
    factory = _session_factory()
    with factory() as session:
        now = utcnow()
        business = BusinessModel(
            id=new_id("business"),
            display_name="Rejected Result Page",
            normalized_name="rejected result page",
            geography="Toronto",
            market_key="toronto",
            status="archived",
            first_seen_at=now,
            last_seen_at=now,
        )
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="website_status",
            label="Website status",
            value_type="text",
            category="website",
            status="active",
            collector_key=None,
            freshness_days=30,
            opportunity_direction="categorical",
            config={"score_values": {"missing": 0}},
            version=1,
        )
        payload = {"website_status": "missing"}
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="configured_search",
            external_id="search-1",
            query_signature="painters in toronto",
            content_hash=stable_content_hash(payload),
            source_url="https://search.example/result",
            raw_payload=payload,
            observed_at=now,
        )
        fact = BusinessFactModel(
            id=new_id("fact"),
            business_id=business.id,
            fact_key=definition.key,
            signal_definition_id=definition.id,
            value_type="text",
            value_text="missing",
            confidence=95,
            attribute_score=0,
            score_version=1,
            score_reason="mapped",
            resolution_state="confirmed",
            supporting_claim_ids=[],
            quality_state="rejected",
            quality_policy_version=1,
            observed_at=now,
            expires_at=now + timedelta(days=30),
            source_observation_id=observation.id,
            resolver_version=1,
        )
        session.add_all([business, definition, observation, fact])
        session.commit()

        result = clean_canonical_facts(session, apply=True)
        assert result.deleted == 1
        assert result.reasons["rejected"] == 1
        assert session.get(SourceObservationModel, observation.id) is not None


def test_domain_age_is_scored_as_supporting_footprint_context() -> None:
    assert score_attribute("domain_age_days", 0).score == 0
    assert score_attribute("domain_age_days", 3650).score == 0
