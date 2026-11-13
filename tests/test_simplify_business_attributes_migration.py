from __future__ import annotations

import importlib
from datetime import datetime, timezone

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    select,
)


def test_simplify_business_attributes_keeps_one_self_contained_attribute(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    attributes = Table(
        "business_attributes",
        metadata,
        Column("id", String(64), primary_key=True),
        Column("business_id", String(64), nullable=False),
        Column("row_type", String(32), nullable=False),
        Column("attribute_key", String(255), nullable=False),
        Column("signal_definition_id", String(64)),
        Column("value_type", String(16), nullable=False),
        Column("value_text", Text),
        Column("value_number", Float),
        Column("value_boolean", Boolean),
        Column("value_json", JSON),
        Column("confidence", Integer, nullable=False),
        Column("attribute_score", Float),
        Column("score_version", Integer),
        Column("score_reason", Text),
        Column("resolution_state", String(32), nullable=False),
        Column("supporting_evidence_ids", JSON, nullable=False),
        Column("observed_at", DateTime(timezone=True), nullable=False),
        Column("expires_at", DateTime(timezone=True)),
        Column("source", String(255)),
        Column("source_external_id", String(255)),
        Column("source_query_signature", String(500)),
        Column("source_content_hash", String(64)),
        Column("source_url", String(1000)),
        Column("evidence", JSON, nullable=False),
        Column("resolver_version", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True)),
        UniqueConstraint(
            "business_id",
            "row_type",
            "attribute_key",
            name="uq_business_attributes_business_type_key",
        ),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        observed_at = datetime(2026, 11, 13, tzinfo=timezone.utc)
        connection.execute(
            attributes.insert(),
            {
                    "id": "evidence-1",
                    "business_id": "business-1",
                    "row_type": "evidence",
                    "attribute_key": "evidence:google_places:1",
                    "value_type": "json",
                    "value_json": {"websiteUri": "https://example.com"},
                    "confidence": 100,
                    "resolution_state": "observed",
                    "supporting_evidence_ids": [],
                    "observed_at": observed_at,
                    "source": "google_places",
                    "source_external_id": "places/1",
                    "source_content_hash": "abc123",
                    "source_url": "https://maps.example/1",
                    "evidence": {"websiteUri": "https://example.com"},
                    "resolver_version": 1,
                },
        )
        connection.execute(
            attributes.insert(),
            {
                    "id": "attribute-1",
                    "business_id": "business-1",
                    "row_type": "attribute",
                    "attribute_key": "website_status",
                    "value_type": "text",
                    "value_text": "present",
                    "confidence": 95,
                    "attribute_score": 0,
                    "resolution_state": "confirmed",
                    "supporting_evidence_ids": ["evidence-1"],
                    "observed_at": observed_at,
                    "evidence": {},
                    "resolver_version": 4,
                },
        )

        migration = importlib.import_module(
            "db.migrations.versions.20261113_0094_simplify_business_attributes"
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )
        migration.upgrade()

        migrated = Table(
            "business_attributes",
            MetaData(),
            autoload_with=connection,
        )
        rows = list(connection.execute(select(migrated)).mappings())

    assert len(rows) == 1
    assert rows[0]["id"] == "attribute-1"
    assert rows[0]["source_provider"] == "google_places"
    assert rows[0]["source_external_id"] == "places/1"
    assert rows[0]["evidence_hash"] == "abc123"
    assert rows[0]["evidence"] == {"websiteUri": "https://example.com"}
    assert rows[0]["opportunity_score"] == 0

    columns = {column["name"] for column in inspect(engine).get_columns("business_attributes")}
    assert "row_type" not in columns
    assert "resolution_state" not in columns
    assert "supporting_evidence_ids" not in columns
    assert "resolver_version" not in columns
    assert "source_provider" in columns
    assert "evidence_hash" in columns
