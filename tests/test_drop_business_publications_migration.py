import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_drop_business_publications_migration_is_idempotent() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "business_publications",
        metadata,
        sa.Column("id", sa.String(length=64), primary_key=True),
    )
    metadata.create_all(engine)

    migration = importlib.import_module(
        "db.migrations.versions.20261112_0087_drop_business_publications"
    )
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()
        assert not sa.inspect(connection).has_table("business_publications")
