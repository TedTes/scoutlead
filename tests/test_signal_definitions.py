from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.claims import FactClaim, FactClaimRepository
from business_facts.repository import BusinessFactKey, BusinessFactRepository, BusinessFactValue
from db.models import BusinessModel, SignalDefinitionModel, SourceObservationModel
from db.session import create_database
from shared.utils import new_id, utcnow
from signal_definitions.repository import SignalDefinitionRepository
from signal_collection.service import SignalCollectionService


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _definition(session) -> SignalDefinitionModel:
    model = SignalDefinitionModel(
        id=new_id("signal"),
        key="website_status",
        label="Website status",
        value_type="text",
        category="website",
        status="active",
        collector_key="website_http",
        extractor_key="website_status",
        freshness_days=30,
        opportunity_direction="missing_is_opportunity",
        config={},
        version=1,
    )
    session.add(model)
    session.commit()
    return model


def _business(session) -> BusinessModel:
    now = utcnow()
    model = BusinessModel(
        id=new_id("business"),
        display_name="Example Painting",
        normalized_name="example painting",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(model)
    session.commit()
    return model


def test_definition_can_be_looked_up_by_key() -> None:
    factory = _session_factory()
    with factory() as session:
        definition = _definition(session)

        found = SignalDefinitionRepository(session).get_by_key("website_status")

        assert found is not None
        assert found.id == definition.id


def test_claim_and_resolved_fact_link_to_definition() -> None:
    factory = _session_factory()
    with factory() as session:
        definition = _definition(session)
        business = _business(session)
        now = utcnow()
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="website_enrichment",
            content_hash="signal-definition-test",
            raw_payload={},
            observed_at=now,
        )
        session.add(observation)
        session.commit()

        claim = FactClaimRepository(session).record(
            FactClaim(
                business_id=business.id,
                fact_key="website_status",
                value="present",
                source_observation_id=observation.id,
                confidence=100,
                extractor="test",
                extractor_version=1,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )
        fact = BusinessFactRepository(session).upsert(
            business.id,
            BusinessFactValue(
                key=BusinessFactKey.WEBSITE_STATUS,
                value="present",
                observed_at=now,
                source_observation_id=observation.id,
            ),
        )

        assert claim.signal_definition_id == definition.id
        assert fact.signal_definition_id == definition.id


def test_dynamic_signal_collects_from_existing_observation() -> None:
    factory = _session_factory()
    with factory() as session:
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="mobile_viewport_present",
            label="Mobile viewport present",
            value_type="boolean",
            category="performance",
            status="active",
            collector_key="existing_observation",
            extractor_key="payload_path",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"payload_path": "website_enrichment.has_mobile_viewport"},
            version=1,
        )
        business = _business(session)
        observation = SourceObservationModel(
            id=new_id("observation"),
            business_id=business.id,
            source="company_website_seed",
            content_hash="dynamic-signal-test",
            raw_payload={"website_enrichment": {"has_mobile_viewport": False}},
            observed_at=utcnow(),
        )
        session.add_all([definition, observation])
        session.commit()

        summary = SignalCollectionService(session).collect(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary == {"requested": 1, "observed": 1, "claimed": 1, "unknown": 0}
        fact = next(fact for fact in business.facts if fact.fact_key == definition.key)
        assert fact.value_boolean is False
        assert fact.signal_definition_id == definition.id
        assert fact.quality_state == "staged"


def test_domain_age_signal_collects_registration_age_from_rdap(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "events": [
                    {
                        "eventAction": "registration",
                        "eventDate": "2020-01-15T00:00:00Z",
                    }
                ]
            }

    monkeypatch.setattr(
        "signal_collection.service.httpx.get",
        lambda *args, **kwargs: Response(),
    )
    factory = _session_factory()
    with factory() as session:
        definition = SignalDefinitionModel(
            id=new_id("signal"),
            key="domain_age_days",
            label="Domain age",
            value_type="number",
            category="website",
            unit="days",
            status="active",
            collector_key="domain_rdap",
            extractor_key="domain_age_days",
            freshness_days=90,
            opportunity_direction="none",
            config={},
            version=1,
        )
        business = _business(session)
        business.website_url = "https://www.example-painting.ca/contact"
        business.domain = "example-painting.ca"
        session.add(definition)
        session.commit()

        summary = SignalCollectionService(session).collect(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary == {"requested": 1, "observed": 1, "claimed": 1, "unknown": 0}
        fact = next(fact for fact in business.facts if fact.fact_key == definition.key)
        assert fact.value_number > 2000
        assert fact.quality_state == "staged"


def test_pagespeed_signals_share_one_mobile_audit(monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "analysisUTCTimestamp": "2026-10-12T12:00:00Z",
                "loadingExperience": {
                    "metrics": {"INTERACTION_TO_NEXT_PAINT": {"percentile": 180}}
                },
                "lighthouseResult": {
                    "finalUrl": "https://example-painting.ca/",
                    "lighthouseVersion": "12.0.0",
                    "categories": {
                        "performance": {"score": 0.64},
                        "accessibility": {"score": 0.91},
                        "best-practices": {"score": 0.87},
                        "seo": {"score": 0.95},
                    },
                    "audits": {
                        "largest-contentful-paint": {"numericValue": 3100},
                        "cumulative-layout-shift": {"numericValue": 0.12},
                        "total-blocking-time": {"numericValue": 240},
                    },
                },
            }

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return Response()

    monkeypatch.setattr("signal_collection.service.httpx.get", fake_get)
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        business.website_url = "https://example-painting.ca"
        definitions = [
            SignalDefinitionModel(
                id=new_id("signal"),
                key="mobile_performance_score",
                label="Mobile performance score",
                value_type="number",
                category="performance",
                unit="score",
                status="active",
                collector_key="pagespeed_mobile",
                extractor_key="pagespeed_performance_score",
                freshness_days=30,
                opportunity_direction="lower_is_opportunity",
                config={
                    "opportunity_threshold": 70,
                    "auto_publish": True,
                    "requires_validation": False,
                },
                version=1,
            ),
            SignalDefinitionModel(
                id=new_id("signal"),
                key="accessibility_score",
                label="Accessibility score",
                value_type="number",
                category="accessibility",
                unit="score",
                status="active",
                collector_key="pagespeed_mobile",
                extractor_key="pagespeed_accessibility_score",
                freshness_days=30,
                opportunity_direction="lower_is_opportunity",
                config={
                    "opportunity_threshold": 90,
                    "auto_publish": True,
                    "requires_validation": False,
                },
                version=1,
            ),
        ]
        session.add_all(definitions)
        session.commit()

        service = SignalCollectionService(session)
        for definition in definitions:
            service.collect(
                definition.id,
                expected_version=1,
                business_ids=[business.id],
            )

        assert len(calls) == 1
        facts = {fact.fact_key: fact for fact in business.facts}
        assert facts["mobile_performance_score"].value_number == 64
        assert facts["accessibility_score"].value_number == 91
        assert facts["mobile_performance_score"].quality_state == "published"
