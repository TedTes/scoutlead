import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_audience_folder_niche_migration_backfills_one_stable_trade_folder() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "niches",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
    )
    sa.Table(
        "audience_folders",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    sa.Table(
        "territories",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("folder_id", sa.String(64), nullable=True),
        sa.Column("niche_id", sa.String(64), nullable=True),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261110_0081_map_audience_folders_to_niches"
    )

    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO niches (id) VALUES ('painting')"))
        connection.execute(
            sa.text(
                """
                INSERT INTO audience_folders
                    (id, workspace_id, product_id, name, sort_order, created_at, updated_at)
                VALUES
                    ('first', 'workspace', 'product', 'Painters', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                    ('second', 'workspace', 'product', 'Campaign', 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO territories (id, folder_id, niche_id)
                VALUES ('one', 'first', 'painting'), ('two', 'second', 'painting')
                """
            )
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        migration.upgrade()

        rows = connection.execute(
            sa.text("SELECT id, niche_id FROM audience_folders ORDER BY sort_order")
        ).all()

    assert rows == [("first", "painting"), ("second", None)]
    columns = {
        column["name"] for column in sa.inspect(engine).get_columns("audience_folders")
    }
    assert "niche_id" in columns
