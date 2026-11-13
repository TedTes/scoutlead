from __future__ import annotations

import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, ForeignKey, MetaData, String, Table, create_engine, inspect


def test_remove_service_catalog_migration_drops_both_tables(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    Table(
        "service_definitions",
        metadata,
        Column("id", String(64), primary_key=True),
    )
    Table(
        "service_signal_mappings",
        metadata,
        Column("id", String(64), primary_key=True),
        Column(
            "service_definition_id",
            ForeignKey("service_definitions.id"),
            nullable=False,
        ),
    )
    metadata.create_all(engine)

    migration = importlib.import_module(
        "db.migrations.versions.20261113_0093_remove_service_catalog"
    )
    with engine.begin() as connection:
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )
        migration.upgrade()

    tables = set(inspect(engine).get_table_names())
    assert "service_signal_mappings" not in tables
    assert "service_definitions" not in tables
