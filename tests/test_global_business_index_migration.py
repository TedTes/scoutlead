import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
)


def _legacy_schema(engine) -> None:
    metadata = MetaData()
    Table("products", metadata, Column("id", String, primary_key=True))
    Table("niches", metadata, Column("id", String, primary_key=True))
    segment = Table(
        "business_index_segments",
        metadata,
        Column("id", String, primary_key=True),
        Column("niche_id", String, ForeignKey("niches.id"), nullable=False),
        Column("product_id", String, ForeignKey("products.id"), nullable=False),
        Column("market_key", String, nullable=False),
        UniqueConstraint(
            "niche_id",
            "market_key",
            name="uq_business_index_segments_niche_market",
        ),
    )
    Index("ix_business_index_segments_niche_id", segment.c.niche_id)
    Index("ix_business_index_segments_product_id", segment.c.product_id)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO products (id) VALUES ('product_1')")
        connection.exec_driver_sql("INSERT INTO niches (id) VALUES ('niche_1')")
        connection.exec_driver_sql(
            "INSERT INTO business_index_segments "
            "(id, niche_id, product_id, market_key) "
            "VALUES ('segment_1', 'niche_1', 'product_1', 'toronto')"
        )


def test_global_segment_migration_removes_product_ownership_idempotently() -> None:
    engine = create_engine("sqlite:///:memory:")
    _legacy_schema(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261021_0060_global_business_index_segments"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        inspector = inspect(connection)
        assert "product_id" not in {
            column["name"]
            for column in inspector.get_columns("business_index_segments")
        }
        assert {
            tuple(foreign_key["constrained_columns"])
            for foreign_key in inspector.get_foreign_keys(
                "business_index_segments"
            )
        } == {("niche_id",)}
        assert "ix_business_index_segments_product_id" not in {
            index["name"]
            for index in inspector.get_indexes("business_index_segments")
        }
        assert "ix_business_index_segments_niche_id" in {
            index["name"]
            for index in inspector.get_indexes("business_index_segments")
        }
        assert connection.exec_driver_sql(
            "SELECT id, niche_id, market_key FROM business_index_segments"
        ).one() == ("segment_1", "niche_1", "toronto")

        migration.upgrade()
        assert "product_id" not in {
            column["name"]
            for column in inspect(connection).get_columns(
                "business_index_segments"
            )
        }
