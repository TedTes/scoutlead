import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from db.base import Base
import db.models  # noqa: F401


REMOVED_TABLES = {
    "quality_labels",
    "quality_metric_snapshots",
    "campaign_insights",
    "demo_sites",
    "product_source_drafts",
    "learning_summaries",
}


def test_removed_feature_migration_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261020_0056_remove_unused_features"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        assert REMOVED_TABLES <= set(inspect(connection).get_table_names())

        migration.upgrade()
        assert REMOVED_TABLES.isdisjoint(inspect(connection).get_table_names())
