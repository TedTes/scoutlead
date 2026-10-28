from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import BusinessFactModel, BusinessModel, SignalDefinitionModel
from db.session import create_database
from shared.utils import utcnow


def test_https_semantics_migration_versions_signal_and_stages_old_fact() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    create_database(engine)
    now = utcnow()
    with Session(engine) as session:
        session.add(
            SignalDefinitionModel(
                id="signal_uses_https",
                key="uses_https",
                label="HTTPS enabled",
                value_type="boolean",
                category="technical",
                status="active",
                collector_key="website_dom",
                extractor_key="uses_https",
                freshness_days=30,
                opportunity_direction="false_is_opportunity",
                config={"requires_validation": True},
                version=2,
            )
        )
        session.add(
            BusinessModel(
                id="business_http_site",
                display_name="HTTP Site",
                normalized_name="http site",
                website_url="http://example.com",
                domain="example.com",
                customer_kind="unknown",
                status="active",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        session.flush()
        session.add(
            BusinessFactModel(
                id="fact_uses_https",
                business_id="business_http_site",
                fact_key="uses_https",
                signal_definition_id="signal_uses_https",
                value_type="boolean",
                value_boolean=False,
                confidence=100,
                resolution_state="confirmed",
                supporting_claim_ids=[],
                quality_state="published",
                quality_policy_version=1,
                observed_at=now,
                resolver_version=1,
            )
        )
        session.commit()

    migration = import_module(
        "db.migrations.versions.20261027_0064_correct_https_signal_semantics"
    )
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            migration.upgrade()

    with Session(engine) as session:
        definition = session.get(SignalDefinitionModel, "signal_uses_https")
        fact = session.get(BusinessFactModel, "fact_uses_https")
        assert definition is not None
        assert definition.version == 3
        assert definition.config["https_semantics"] == "available"
        assert definition.config["protocol_evidence_version"] == 1
        assert fact is not None
        assert fact.quality_state == "staged"
