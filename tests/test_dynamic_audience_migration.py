import importlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    JSON,
    Column,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    inspect,
)


def test_dynamic_audience_migration_is_idempotent_and_preserves_primary_niche() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    Table(
        "niches",
        metadata,
        Column("id", String, primary_key=True),
        Column("slug", String, nullable=False),
    )
    Table(
        "territories",
        metadata,
        Column("id", String, primary_key=True),
        Column("niche_id", String, nullable=False),
        Column("city", String),
        Column("trade_keys", JSON, nullable=False),
        UniqueConstraint(
            "niche_id",
            "city",
            name="uq_territories_workspace_offer_niche_market_criteria",
        ),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261023_0061_dynamic_audience_profiles"
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO niches (id, slug) VALUES "
            "('niche_1', 'home_service_painting')"
        )
        connection.exec_driver_sql(
            "INSERT INTO territories (id, niche_id, city, trade_keys) VALUES "
            "('audience_1', 'niche_1', 'Toronto', '[\"painters\", \"roofers\"]')"
        )
        migration.op = Operations(MigrationContext.configure(connection))

        migration.upgrade()
        migration.upgrade()

        inspector = inspect(connection)
        niche_columns = {
            column["name"] for column in inspector.get_columns("niches")
        }
        territory_columns = {
            column["name"] for column in inspector.get_columns("territories")
        }
        audience = connection.exec_driver_sql(
            "SELECT niche_id, city, place_label FROM territories"
        ).one()
        search_config = connection.exec_driver_sql(
            "SELECT search_config FROM niches WHERE id = 'niche_1'"
        ).scalar_one()

        assert "search_config" in niche_columns
        assert "trade_keys" not in territory_columns
        assert {
            "place_label",
            "place_provider",
            "place_external_id",
            "country_code",
        } <= territory_columns
        assert audience == ("niche_1", "Toronto", "Toronto")
        assert "include_terms" in search_config
        assert "ix_territories_country_code" in {
            index["name"] for index in inspector.get_indexes("territories")
        }
        assert "uq_territories_workspace_offer_niche_market_criteria" not in {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("territories")
        }
