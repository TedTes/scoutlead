import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from db.base import Base
import db.models  # noqa: F401


RETIRED_TABLES = {
    "quality_labels",
    "quality_metric_snapshots",
    "campaign_insights",
    "demo_sites",
    "product_source_drafts",
    "learning_summaries",
}


def test_compatibility_migration_keeps_retired_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    for table_name in RETIRED_TABLES:
        Table(table_name, metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    migration = importlib.import_module(
        "db.migrations.versions.20261020_0056_remove_unused_features"
    )

    with engine.begin() as connection:
        migration.upgrade()
        assert RETIRED_TABLES <= set(inspect(connection).get_table_names())

        migration.downgrade()
        assert RETIRED_TABLES <= set(inspect(connection).get_table_names())


def test_follow_up_migration_drops_retired_tables() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261020_0057_drop_retired_feature_tables"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        assert RETIRED_TABLES <= set(inspect(connection).get_table_names())

        migration.upgrade()
        assert RETIRED_TABLES.isdisjoint(inspect(connection).get_table_names())
