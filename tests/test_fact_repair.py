from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.claims import FactClaim, FactClaimRepository
from business_facts.repository import BusinessFactRepository, BusinessFactValue
from canonical.repository import CanonicalRepository
from db.models import BusinessFactModel, BusinessModel, SignalDefinitionModel
from db.session import create_database
from quality.fact_repair import repair_current_facts
from shared.utils import utcnow


def test_fact_repair_relinks_intact_claim_and_deletes_irrecoverable_unknown() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        definition = SignalDefinitionModel(
            id="signal_contact_form_present",
            key="contact_form_present",
            label="Contact form present",
            value_type="boolean",
            category="conversion",
            status="active",
            collector_key="website_dom",
            extractor_key="contact_form",
            freshness_days=30,
            opportunity_direction="false_is_opportunity",
            config={"minimum_confidence": 90},
            version=1,
        )
        unknown_definition = SignalDefinitionModel(
            id="signal_website_status",
            key="website_status",
            label="Website status",
            value_type="text",
            category="website",
            status="active",
            collector_key="website_http",
            extractor_key="website_status",
            freshness_days=30,
            opportunity_direction="missing_is_opportunity",
            config={"minimum_confidence": 90},
            version=1,
        )
        session.add_all([definition, unknown_definition])
        session.commit()

        first = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Repairable Electric",
            geography="Toronto",
            source="company_website_signal",
            raw={"external_id": "repair/old", "has_contact_form": True},
        )
        business = session.get(BusinessModel, first.business_id)
        assert business is not None
        second = CanonicalRepository(session).record_business_evidence(
            business=business,
            source="company_website_signal",
            raw={"external_id": "repair/new", "has_contact_form": False},
        )
        now = utcnow()
        old_claim = FactClaimRepository(session).record(
            FactClaim(
                business_id=first.business_id,
                fact_key="contact_form_present",
                value=True,
                source_observation_id=first.source_observation_id,
                confidence=95,
                extractor="contact_form",
                extractor_version=3,
                observed_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=29),
                signal_definition_id=definition.id,
            )
        )
        claim = FactClaimRepository(session).record(
            FactClaim(
                business_id=first.business_id,
                fact_key="contact_form_present",
                value=False,
                source_observation_id=second.source_observation_id,
                confidence=95,
                extractor="contact_form",
                extractor_version=3,
                observed_at=now,
                expires_at=now + timedelta(days=30),
                signal_definition_id=definition.id,
            )
        )
        fact = BusinessFactRepository(session).upsert(
            first.business_id,
            BusinessFactValue(
                key="contact_form_present",
                value=True,
                observed_at=old_claim.observed_at,
                expires_at=old_claim.expires_at,
                source_observation_id=first.source_observation_id,
                supporting_claim_ids=(old_claim.id,),
                quality_state="published",
            ),
        )

        unknown_link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Unknown Painter",
            geography="Toronto",
            source="company_website_signal",
            raw={"external_id": "unknown/painter", "status": "unknown"},
        )
        unknown = BusinessFactRepository(session).upsert(
            unknown_link.business_id,
            BusinessFactValue(
                key="website_status",
                value="unknown",
                observed_at=now,
                expires_at=now + timedelta(days=30),
                source_observation_id=unknown_link.source_observation_id,
                quality_state="staged",
            ),
        )
        session.commit()

        dry_run = repair_current_facts(session)
        assert dry_run.repaired == 1
        assert dry_run.deleted_irrecoverable == 1
        assert fact.source_observation_id == first.source_observation_id
        assert session.get(BusinessFactModel, unknown.id) is not None

        applied = repair_current_facts(session, apply=True)
        repaired = session.get(BusinessFactModel, fact.id)
        assert applied.repaired == 1
        assert repaired is not None
        assert repaired.value_boolean is False
        assert repaired.source_observation_id == second.source_observation_id
        assert repaired.supporting_claim_ids == [claim.id]
        assert repaired.resolution_state == "conflicted"
        assert repaired.quality_state == "staged"
        assert session.get(BusinessFactModel, unknown.id) is None

        repaired.quality_state = "rejected"
        repaired.quality_policy_version = 4
        repaired.confidence = 0
        session.commit()
        repeated = repair_current_facts(session)
        assert repeated.repaired == 0
        assert repeated.deleted_irrecoverable == 0
