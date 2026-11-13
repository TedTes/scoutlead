from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, create_engine, insert, select


MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "agent"
    / "db"
    / "migrations"
    / "versions"
    / "20261113_0096_remove_duplicated_attribute_payloads.py"
)


def test_migration_keeps_one_source_payload_and_clears_derived_copies() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    attributes = Table(
        "business_attributes",
        metadata,
        Column("id", String(64), primary_key=True),
        Column("business_id", String(64), nullable=False),
        Column("attribute_key", String(255), nullable=False),
        Column("source_provider", String(255)),
        Column("value_type", String(16), nullable=False, default="text"),
        Column("value_text", String),
        Column("evidence", JSON, nullable=False),
        Column("observed_at", DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    payload = {"name": "Example Plumbing", "large_provider_field": [1, 2, 3]}

    with engine.begin() as connection:
        connection.execute(
            insert(attributes),
            [
                {
                    "id": "name",
                    "business_id": "business_1",
                    "attribute_key": "business_name",
                    "source_provider": "google_places",
                    "value_type": "text",
                    "value_text": "Example Plumbing",
                    "evidence": payload,
                },
                {
                    "id": "website",
                    "business_id": "business_1",
                    "attribute_key": "website_status",
                    "source_provider": "google_places",
                    "value_type": "text",
                    "value_text": "present",
                    "evidence": payload,
                },
                {
                    "id": "rating",
                    "business_id": "business_1",
                    "attribute_key": "google_rating",
                    "source_provider": "google_places",
                    "value_type": "number",
                    "value_text": None,
                    "evidence": payload,
                },
            ],
        )
        module = _migration_module()
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()

        rows = {
            row["attribute_key"]: row["evidence"]
            for row in connection.execute(select(attributes)).mappings()
        }

    assert rows["__source_payload__:google_places"] == payload
    assert rows["business_name"] == {}
    assert rows["website_status"] == {}
    assert rows["google_rating"] == {}


def _migration_module():
    spec = importlib.util.spec_from_file_location("migration_0096", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
