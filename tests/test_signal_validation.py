from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.models import (
    BusinessFactModel,
    BusinessModel,
    FactClaimModel,
    QualityMetricSnapshotModel,
    SignalDefinitionModel,
    SourceObservationModel,
    ValidationResultModel,
)
from db.session import create_database
from shared.utils import new_id, utcnow
from signal_collection.service import SignalCollectionService
from signal_validation.service import SignalValidationService


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _business(session) -> BusinessModel:
    now = utcnow()
    business = BusinessModel(
        id=new_id("business"),
        display_name="Example Services",
        normalized_name="example services",
        status="active",
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(business)
    session.commit()
    return business


def _definition(session, *, config: dict | None = None) -> SignalDefinitionModel:
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
        config={
            "payload_path": "website_enrichment.has_mobile_viewport",
            "auto_publish": False,
            "requires_validation": True,
            **(config or {}),
        },
        version=1,
    )
    session.add(definition)
    session.commit()
    return definition


def _observation(session, business_id: str, value: bool, *, offset_minutes: int = 0):
    observed_at = utcnow() + timedelta(minutes=offset_minutes)
    observation = SourceObservationModel(
        id=new_id("observation"),
        business_id=business_id,
        source="company_website_signal",
        content_hash=new_id("content"),
        raw_payload={
            "website_enrichment": {
                "has_mobile_viewport": value,
                "inspection": {
                    "complete": True,
                    "pages": [
                        {
                            "url": "https://example.test",
                            "status_code": 200,
                            "dom_complete": True,
                        }
                    ],
                },
                "signal_evidence": {
                    "mobile_viewport_present": (
                        [
                            {
                                "url": "https://example.test",
                                "match": "viewport meta declaration",
                            }
                        ]
                        if value
                        else []
                    )
                },
            }
        },
        observed_at=observed_at,
    )
    session.add(observation)
    session.commit()
    return observation


def _collect(session, definition, business) -> BusinessFactModel:
    SignalCollectionService(session).collect(
        definition.id,
        expected_version=definition.version,
        business_ids=[business.id],
    )
    fact = session.scalar(
        select(BusinessFactModel).where(
            BusinessFactModel.business_id == business.id,
            BusinessFactModel.signal_definition_id == definition.id,
        )
    )
    assert fact is not None
    return fact


def _passing_mobile_viewport_metric(session) -> None:
    session.add(
        QualityMetricSnapshotModel(
            id=new_id("quality_metric"),
            dimension="missing_mobile_viewport",
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


def test_signal_validation_publishes_reproducible_claim() -> None:
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        definition = _definition(session)
        _passing_mobile_viewport_metric(session)
        _observation(session, business.id, True)
        fact = _collect(session, definition, business)
        assert fact.quality_state == "staged"

        summary = SignalValidationService(session).validate(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary["published"] == 1
        assert fact.quality_state == "published"
        result = session.scalar(select(ValidationResultModel))
        assert result is not None
        assert result.status == "passed"
        assert result.validation_type == "signal:mobile_viewport_present"


def test_existing_auto_publish_definition_stages_until_validation() -> None:
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        definition = _definition(session)
        definition.config = {
            "payload_path": "website_enrichment.has_mobile_viewport",
            "auto_publish": True,
        }
        session.commit()
        _observation(session, business.id, True)

        fact = _collect(session, definition, business)

        assert fact.quality_state == "staged"


def test_signal_validation_keeps_conflicting_claim_for_review() -> None:
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        definition = _definition(session)
        _observation(session, business.id, True)
        _collect(session, definition, business)
        _observation(session, business.id, False, offset_minutes=1)
        fact = _collect(session, definition, business)

        summary = SignalValidationService(session).validate(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary["needs_review"] == 1
        assert fact.quality_state == "staged"
        result = session.scalar(
            select(ValidationResultModel).order_by(
                ValidationResultModel.observed_at.desc()
            )
        )
        assert result is not None
        assert result.status == "uncertain"
        assert "disagree" in result.reason


def test_signal_validation_rejects_claim_that_cannot_be_reproduced() -> None:
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        definition = _definition(session)
        _observation(session, business.id, True)
        fact = _collect(session, definition, business)
        claim = fact.supporting_claim_ids[0]
        stored_claim = session.get(FactClaimModel, claim)
        assert stored_claim is not None
        stored_claim.value = False
        session.commit()

        summary = SignalValidationService(session).validate(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary["rejected"] == 1
        assert fact.quality_state == "rejected"
        result = session.scalar(select(ValidationResultModel))
        assert result is not None
        assert result.status == "failed"


def test_signal_validation_respects_manual_validation_mode() -> None:
    factory = _session_factory()
    with factory() as session:
        business = _business(session)
        definition = _definition(session, config={"validation_mode": "manual"})
        _observation(session, business.id, True)
        fact = _collect(session, definition, business)

        summary = SignalValidationService(session).validate(
            definition.id,
            expected_version=1,
            business_ids=[business.id],
        )

        assert summary["needs_review"] == 1
        assert fact.quality_state == "staged"
