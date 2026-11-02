from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_migration_quarantines_unreviewed_non_business_map_entities() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    businesses = sa.Table(
        "businesses",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("status", sa.String, nullable=False),
    )
    observations = sa.Table(
        "source_observations",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("business_id", sa.String, nullable=False),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("raw_payload", sa.JSON, nullable=False),
    )
    facts = sa.Table(
        "business_facts",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("business_id", sa.String, nullable=False),
        sa.Column("quality_state", sa.String, nullable=False),
        sa.Column("resolution_state", sa.String, nullable=False),
    )
    results = sa.Table(
        "audience_results",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("business_id", sa.String, nullable=False),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("shortlisted_at", sa.DateTime, nullable=True),
        sa.Column("contacted_at", sa.DateTime, nullable=True),
        sa.Column("outreach_lead_id", sa.String, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            businesses.insert(),
            [
                {"id": "bad", "status": "active"},
                {"id": "good", "status": "active"},
            ],
        )
        connection.execute(
            observations.insert(),
            [
                {
                    "id": "observation_bad_osm",
                    "business_id": "bad",
                    "source": "openstreetmap",
                    "raw_payload": {
                        "raw": {
                            "tags": {
                                "name": "Bellamy Rd N at Painted Post Dr",
                                "highway": "bus_stop",
                                "public_transport": "platform",
                            }
                        }
                    },
                },
                {
                    "id": "observation_bad_google",
                    "business_id": "bad",
                    "source": "google_places",
                    "raw_payload": {"types": ["intersection"]},
                },
                {
                    "id": "observation_good",
                    "business_id": "good",
                    "source": "google_places",
                    "raw_payload": {"types": ["painter", "establishment"]},
                },
            ],
        )
        connection.execute(
            facts.insert(),
            [
                {
                    "id": "fact_bad",
                    "business_id": "bad",
                    "quality_state": "published",
                    "resolution_state": "confirmed",
                },
                {
                    "id": "fact_good",
                    "business_id": "good",
                    "quality_state": "published",
                    "resolution_state": "confirmed",
                },
            ],
        )
        connection.execute(
            results.insert(),
            [
                {
                    "id": "unreviewed",
                    "business_id": "bad",
                    "reviewed_at": None,
                    "shortlisted_at": None,
                    "contacted_at": None,
                    "outreach_lead_id": None,
                },
                {
                    "id": "reviewed",
                    "business_id": "bad",
                    "reviewed_at": None,
                    "shortlisted_at": None,
                    "contacted_at": None,
                    "outreach_lead_id": "lead_1",
                },
                {
                    "id": "good_result",
                    "business_id": "good",
                    "reviewed_at": None,
                    "shortlisted_at": None,
                    "contacted_at": None,
                    "outreach_lead_id": None,
                },
            ],
        )

        migration = import_module(
            "db.migrations.versions.20261102_0069_reject_non_business_map_entities"
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()

        assert connection.scalar(
            sa.select(businesses.c.status).where(businesses.c.id == "bad")
        ) == "quarantined"
        assert connection.scalar(
            sa.select(businesses.c.status).where(businesses.c.id == "good")
        ) == "active"
        assert connection.execute(
            sa.select(facts.c.quality_state, facts.c.resolution_state).where(
                facts.c.id == "fact_bad"
            )
        ).one() == ("rejected", "unknown")
        assert set(connection.scalars(sa.select(results.c.id))) == {
            "reviewed",
            "good_result",
        }
