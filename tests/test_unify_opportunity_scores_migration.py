from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_migration_rescores_existing_facts_as_lead_opportunities() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("opportunity_direction", sa.String, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
    )
    facts = sa.Table(
        "business_facts",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("fact_key", sa.String, nullable=False),
        sa.Column("value_type", sa.String, nullable=False),
        sa.Column("value_text", sa.String, nullable=True),
        sa.Column("value_number", sa.Float, nullable=True),
        sa.Column("value_boolean", sa.Boolean, nullable=True),
        sa.Column("attribute_score", sa.Float, nullable=True),
        sa.Column("score_version", sa.Integer, nullable=True),
        sa.Column("score_reason", sa.String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            definitions.insert(),
            [
                {
                    "id": "website",
                    "key": "website_status",
                    "opportunity_direction": "missing_is_opportunity",
                    "config": {
                        "audience_max_score": 49.999,
                        "opportunity_values": ["missing", "not_listed"],
                    },
                    "version": 1,
                },
                {
                    "id": "form",
                    "key": "contact_form_present",
                    "opportunity_direction": "false_is_opportunity",
                    "config": {},
                    "version": 1,
                },
            ],
        )
        connection.execute(
            facts.insert(),
            [
                {
                    "id": "missing_website",
                    "fact_key": "website_status",
                    "value_type": "text",
                    "value_text": "missing",
                    "value_number": None,
                    "value_boolean": None,
                    "attribute_score": 0,
                    "score_version": 1,
                },
                {
                    "id": "not_listed",
                    "fact_key": "website_status",
                    "value_type": "text",
                    "value_text": "not_listed",
                    "value_number": None,
                    "value_boolean": None,
                    "attribute_score": 55,
                    "score_version": 1,
                },
                {
                    "id": "form_present",
                    "fact_key": "contact_form_present",
                    "value_type": "boolean",
                    "value_text": None,
                    "value_number": None,
                    "value_boolean": True,
                    "attribute_score": 100,
                    "score_version": 1,
                },
                {
                    "id": "form_missing",
                    "fact_key": "contact_form_present",
                    "value_type": "boolean",
                    "value_text": None,
                    "value_number": None,
                    "value_boolean": False,
                    "attribute_score": 0,
                    "score_version": 1,
                },
            ],
        )

        migration = import_module(
            "db.migrations.versions.20261102_0070_unify_opportunity_scores"
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        scores = dict(
            connection.execute(
                sa.select(facts.c.id, facts.c.attribute_score)
            ).all()
        )
        assert scores == {
            "missing_website": 100,
            "not_listed": None,
            "form_present": 0,
            "form_missing": 100,
        }
        config = connection.scalar(
            sa.select(definitions.c.config).where(definitions.c.id == "website")
        )
        assert config["audience_min_score"] == 50.001
        assert config["opportunity_values"] == ["missing"]
