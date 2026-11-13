import importlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


RETIRED_TABLES = {
    "business_facts",
    "fact_claims",
    "source_observations",
    "validation_results",
    "business_fact_changes",
    "business_search_evaluations",
}


def test_bulk_insert_updates_an_existing_canonical_attribute() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    attributes = sa.Table(
        "business_attributes",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_id", sa.String(64), nullable=False),
        sa.Column("row_type", sa.String(32), nullable=False),
        sa.Column("attribute_key", sa.String(255), nullable=False),
        sa.Column("value_text", sa.Text()),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_id",
            "row_type",
            "attribute_key",
            name="uq_business_attributes_business_type_key",
        ),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261112_0088_consolidate_business_attributes"
    )
    created_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    migrated_at = datetime(2026, 11, 12, tzinfo=timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            attributes.insert(),
            {
                "id": "existing_attribute",
                "business_id": "business_1",
                "row_type": "attribute",
                "attribute_key": "website_status",
                "value_text": "present",
                "confidence": 50,
                "created_at": created_at,
                "updated_at": created_at,
            },
        )
        migration._bulk_insert(
            connection,
            attributes,
            [
                {
                    "id": "legacy_fact",
                    "business_id": "business_1",
                    "row_type": "attribute",
                    "attribute_key": "website_status",
                    "value_text": "missing",
                    "confidence": 95,
                    "created_at": migrated_at,
                    "updated_at": migrated_at,
                }
            ],
        )

        rows = list(connection.execute(sa.select(attributes)).mappings())
        assert len(rows) == 1
        assert rows[0]["id"] == "existing_attribute"
        assert rows[0]["value_text"] == "missing"
        assert rows[0]["confidence"] == 95
        assert rows[0]["created_at"] == created_at.replace(tzinfo=None)
        assert rows[0]["updated_at"] == migrated_at.replace(tzinfo=None)


def test_consolidation_preserves_attributes_and_evidence_before_dropping_old_tables() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    businesses = sa.Table(
        "businesses",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
    )
    signal_definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
    )
    observations = sa.Table(
        "source_observations",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("query_signature", sa.String(500)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    facts = sa.Table(
        "business_facts",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_id", sa.String(64), nullable=False),
        sa.Column("fact_key", sa.String(255), nullable=False),
        sa.Column("signal_definition_id", sa.String(64)),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("value_text", sa.Text()),
        sa.Column("value_number", sa.Float()),
        sa.Column("value_boolean", sa.Boolean()),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("attribute_score", sa.Float()),
        sa.Column("score_version", sa.Integer()),
        sa.Column("score_reason", sa.Text()),
        sa.Column("resolution_state", sa.String(32)),
        sa.Column("source_observation_id", sa.String(64)),
        sa.Column("supporting_claim_ids", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("resolver_version", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    claims = sa.Table(
        "fact_claims",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_observation_id", sa.String(64), nullable=False),
    )
    memberships = sa.Table(
        "business_niche_memberships",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_observation_id", sa.String(64)),
    )
    seed_batches = sa.Table(
        "seed_batches",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_observation_count", sa.Integer(), nullable=False),
    )
    for table_name in RETIRED_TABLES - {
        "source_observations",
        "business_facts",
        "fact_claims",
    }:
        sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.String(64), primary_key=True),
        )
    metadata.create_all(engine)

    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    payload = {"name": "Example Electric", "website": None}
    with engine.begin() as connection:
        connection.execute(businesses.insert(), {"id": "business_1"})
        connection.execute(signal_definitions.insert(), {"id": "signal_1"})
        connection.execute(
            observations.insert(),
            {
                "id": "observation_1",
                "business_id": "business_1",
                "source": "google_places",
                "external_id": "places/1",
                "query_signature": "query-hash",
                "content_hash": "content-hash",
                "source_url": "https://example.test/source",
                "raw_payload": payload,
                "observed_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            observations.insert(),
            {
                "id": "observation_2",
                "business_id": "business_1",
                "source": "openstreetmap",
                "external_id": "osm/1",
                "query_signature": "osm-query-hash",
                "content_hash": "osm-content-hash",
                "source_url": "https://example.test/osm",
                "raw_payload": {"name": "Example Electric"},
                "observed_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            claims.insert(),
            {"id": "claim_legacy", "source_observation_id": "observation_2"},
        )
        connection.execute(
            facts.insert(),
            {
                "id": "fact_1",
                "business_id": "business_1",
                "fact_key": "website_status",
                "signal_definition_id": "signal_1",
                "value_type": "text",
                "value_text": "missing",
                "confidence": 95,
                "attribute_score": 100,
                "score_version": 2,
                "score_reason": "Verified missing website",
                "resolution_state": "confirmed",
                "source_observation_id": "observation_1",
                "supporting_claim_ids": ["claim_legacy"],
                "observed_at": now,
                "resolver_version": 4,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            memberships.insert(),
            {"id": "membership_1", "source_observation_id": "observation_1"},
        )
        connection.execute(
            seed_batches.insert(),
            {"id": "batch_1", "source_observation_count": 1},
        )

        migration = importlib.import_module(
            "db.migrations.versions.20261112_0088_consolidate_business_attributes"
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert RETIRED_TABLES.isdisjoint(inspector.get_table_names())
        assert "source_observation_id" not in {
            column["name"]
            for column in inspector.get_columns("business_niche_memberships")
        }
        assert "evidence_record_count" in {
            column["name"] for column in inspector.get_columns("seed_batches")
        }

        attributes = sa.Table(
            "business_attributes", sa.MetaData(), autoload_with=connection
        )
        rows = {
            (row["row_type"], row["id"]): dict(row)
            for row in connection.execute(sa.select(attributes)).mappings()
        }
        assert rows[("evidence", "observation_1")]["value_json"] == payload
        attribute = rows[("attribute", "fact_1")]
        assert attribute["attribute_key"] == "website_status"
        assert attribute["value_text"] == "missing"
        assert attribute["source"] == "google_places"
        assert attribute["source_external_id"] == "places/1"
        assert attribute["source_url"] == "https://example.test/source"
        assert attribute["evidence"] == payload
        assert attribute["supporting_evidence_ids"] == [
            "observation_1",
            "observation_2",
        ]
        assert "claim_legacy" not in attribute["supporting_evidence_ids"]
