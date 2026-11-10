import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_niche_catalog_order_migration_is_idempotent() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "niches",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
    )
    sa.Table(
        "workspaces",
        metadata,
        sa.Column("id", sa.String(255), primary_key=True),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261110_0082_order_niche_catalog"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()

    columns = {
        column["name"]: column for column in sa.inspect(engine).get_columns("niches")
    }
    assert columns["display_order"]["nullable"] is False
    assert columns["catalog_status"]["nullable"] is False
    assert "created_by_workspace_id" in columns
    assert sa.inspect(engine).has_table("workspace_niche_preferences")
