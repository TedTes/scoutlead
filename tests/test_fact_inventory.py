from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from business_facts.repository import BusinessFactRepository, BusinessFactValue
from canonical.repository import CanonicalRepository
from db.models import BusinessFactModel, SignalDefinitionModel
from db.session import create_database
from quality.fact_inventory import audit_fact_inventory
from shared.utils import utcnow


def test_fact_inventory_rejects_wrong_source_contract_and_repairs_definition_link() -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            SignalDefinitionModel(
                id="signal_google_rating",
                key="google_rating",
                label="Google rating",
                value_type="number",
                category="reputation",
                status="active",
                collector_key="google_places",
                extractor_key="google_rating",
                freshness_days=30,
                opportunity_direction="lower_is_opportunity",
                config={"minimum_confidence": 90},
                version=1,
            )
        )
        session.commit()
        link = CanonicalRepository(session).upsert_from_discovery_result(
            company_name="Wrong Rating Source",
            geography="Toronto",
            source="company_website_signal",
            raw={"rating": 4.8, "external_id": "website/wrong-rating"},
        )
        fact = BusinessFactRepository(session).upsert(
            link.business_id,
            BusinessFactValue(
                key="google_rating",
                value=4.8,
                observed_at=utcnow(),
                expires_at=utcnow() + timedelta(days=10),
                source_observation_id=link.source_observation_id,
                quality_state="published",
            ),
        )
        fact.signal_definition_id = None
        session.commit()

        dry_run = audit_fact_inventory(session, include_details=True)
        assert dry_run.issues["definition_link_mismatch"] == 1
        assert dry_run.issues["source_contract_mismatch"] == 1
        assert fact.quality_state == "published"

        applied = audit_fact_inventory(session, apply=True)
        assert applied.repaired_definition_links == 1
        assert applied.rejected == 1
        repaired = session.get(BusinessFactModel, fact.id)
        assert repaired.signal_definition_id is not None
        assert repaired.quality_state == "rejected"
        assert repaired.confidence == 0
