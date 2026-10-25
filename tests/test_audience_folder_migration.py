import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_audience_folder_migration_is_idempotent() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table("workspaces", metadata, sa.Column("id", sa.String(255), primary_key=True))
    sa.Table(
        "products",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(255), sa.ForeignKey("workspaces.id")),
    )
    sa.Table(
        "territories",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261025_0062_audience_folders"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        inspector = sa.inspect(connection)

        assert inspector.has_table("audience_folders")
        assert "folder_id" in {
            column["name"] for column in inspector.get_columns("territories")
        }
        assert "ix_territories_folder_id" in {
            index["name"] for index in inspector.get_indexes("territories")
        }
