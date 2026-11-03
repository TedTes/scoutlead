from importlib import import_module

import sqlalchemy as sa


def test_retire_https_removes_sales_paths_but_preserves_definition(monkeypatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    services = sa.Table(
        "service_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("description", sa.Text),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    mappings = sa.Table(
        "service_signal_mappings",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("service_definition_id", sa.String, nullable=False),
        sa.Column("signal_definition_id", sa.String, nullable=False),
    )
    territories = sa.Table(
        "territories",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("signal_keys", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)

    migration = import_module(
        "db.migrations.versions.20261103_0075_retire_https_opportunity"
    )
    now = migration.datetime.now(migration.timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            definitions.insert(),
            {
                "id": "signal_uses_https",
                "key": "uses_https",
                "status": "active",
                "version": 1,
                "updated_at": now,
            },
        )
        connection.execute(
            services.insert(),
            {
                "id": "service_website_upgrade",
                "key": "website_upgrade",
                "description": "Security and website quality gaps.",
                "version": 1,
                "updated_at": now,
            },
        )
        connection.execute(
            mappings.insert(),
            {
                "id": "mapping_https",
                "service_definition_id": "service_website_upgrade",
                "signal_definition_id": "signal_uses_https",
            },
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory_https",
                "signal_keys": ["uses_https", "performance_score"],
                "updated_at": now,
            },
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        definition = connection.execute(sa.select(definitions)).mappings().one()
        assert definition["status"] == "inactive"
        assert connection.scalar(sa.select(sa.func.count()).select_from(mappings)) == 0
        territory = connection.execute(sa.select(territories)).mappings().one()
        assert territory["signal_keys"] == ["performance_score"]
        description = connection.scalar(
            sa.select(services.c.description).where(
                services.c.key == "website_upgrade"
            )
        )
        assert "security" not in description.lower()
