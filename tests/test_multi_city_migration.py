import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, UniqueConstraint, create_engine, inspect


def test_multi_city_migration_adds_locations_and_scopes_coverage_by_market() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    Table(
        "territories",
        metadata,
        Column("id", String, primary_key=True),
    )
    Table(
        "coverage_requests",
        metadata,
        Column("id", String, primary_key=True),
        Column("run_id", String, nullable=False),
        Column("niche_id", String, nullable=False),
        Column("market_key", String, nullable=False),
        UniqueConstraint("run_id", "niche_id", name="uq_coverage_requests_run_niche"),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261111_0084_add_multi_city_searches"
    )

    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = inspect(connection)
        assert "locations" in {
            column["name"] for column in inspector.get_columns("territories")
        }
        assert {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("coverage_requests")
        } == {"uq_coverage_requests_run_niche_market"}

        connection.exec_driver_sql(
            "INSERT INTO coverage_requests (id, run_id, niche_id, market_key) VALUES "
            "('one', 'run', 'niche', 'toronto'), "
            "('two', 'run', 'niche', 'ottawa')"
        )
