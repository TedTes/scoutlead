from importlib import import_module

import sqlalchemy as sa


def test_service_catalog_repair_is_idempotent(monkeypatch) -> None:
    migration = import_module(
        "db.migrations.versions.20261015_0052_repair_service_catalog"
    )
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    services = sa.Table(
        "service_definitions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("key", sa.String(128), unique=True, nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    signals = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("key", sa.String(128), unique=True, nullable=False),
    )
    mappings = sa.Table(
        "service_signal_mappings",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_definition_id", sa.String(64), nullable=False),
        sa.Column("signal_definition_id", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("service_definition_id", "signal_definition_id"),
    )
    metadata.create_all(engine)

    signal_keys = sorted(
        {
            signal_key
            for *_, mapped_signal_keys in migration.SERVICES
            for signal_key in mapped_signal_keys
        }
    )
    with engine.begin() as connection:
        connection.execute(
            signals.insert(),
            [{"id": f"signal_{index}", "key": key} for index, key in enumerate(signal_keys)],
        )
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)

        migration.upgrade()
        migration.upgrade()

        service_rows = connection.execute(
            sa.select(services.c.key, services.c.status)
        ).all()
        mapping_count = connection.scalar(sa.select(sa.func.count()).select_from(mappings))

    assert len(service_rows) == len(migration.SERVICES)
    assert dict(service_rows)["website_modernization"] == "active"
    assert mapping_count == sum(len(service[-1]) for service in migration.SERVICES)
