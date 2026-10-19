from importlib import import_module

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import BusinessFactModel, BusinessModel, SignalDefinitionModel
from db.session import create_database
from shared.utils import utcnow


def test_migration_stages_old_website_facts_and_requires_new_evidence(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    create_database(engine)
    now = utcnow()
    with Session(engine) as session:
        session.add_all(
            [
                BusinessModel(
                    id="business_test",
                    display_name="Test Business",
                    normalized_name="test business",
                    status="active",
                    first_seen_at=now,
                    last_seen_at=now,
                ),
                SignalDefinitionModel(
                    id="signal_test",
                    key="uses_https",
                    label="HTTPS enabled",
                    value_type="boolean",
                    category="technical",
                    status="active",
                    collector_key="website_dom",
                    extractor_key="uses_https",
                    freshness_days=30,
                    opportunity_direction="false_is_opportunity",
                    config={"auto_publish": True},
                    version=1,
                ),
                BusinessFactModel(
                    id="fact_test",
                    business_id="business_test",
                    fact_key="uses_https",
                    signal_definition_id="signal_test",
                    value_type="boolean",
                    value_boolean=False,
                    confidence=100,
                    resolution_state="confirmed",
                    supporting_claim_ids=[],
                    quality_state="published",
                    quality_policy_version=1,
                    observed_at=now,
                    resolver_version=1,
                ),
            ]
        )
        session.commit()

    migration = import_module(
        "db.migrations.versions.20261019_0055_harden_website_signal_evidence"
    )
    with engine.begin() as connection:
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

    with Session(engine) as session:
        fact = session.get(BusinessFactModel, "fact_test")
        definition = session.get(SignalDefinitionModel, "signal_test")
        assert fact is not None and fact.quality_state == "staged"
        assert definition is not None and definition.version == 2
        assert definition.config["requires_validation"] is True
        assert definition.config["evidence_contract_version"] == 2
