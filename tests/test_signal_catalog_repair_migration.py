from importlib import import_module

import sqlalchemy as sa


def test_signal_catalog_repair_restores_signals_mappings_and_fact_links(monkeypatch) -> None:
    service_migration = import_module(
        "db.migrations.versions.20261015_0052_repair_service_catalog"
    )
    signal_migration = import_module(
        "db.migrations.versions.20261016_0053_repair_signal_catalog"
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
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("value_type", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("collector_key", sa.String(128)),
        sa.Column("extractor_key", sa.String(128)),
        sa.Column("freshness_days", sa.Integer, nullable=False),
        sa.Column("opportunity_direction", sa.String(32), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
    fact_tables = [
        sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("fact_key", sa.String(128), nullable=False),
            sa.Column("signal_definition_id", sa.String(64)),
        )
        for table_name in ("fact_claims", "business_facts")
    ]
    metadata.create_all(engine)

    with engine.begin() as connection:
        monkeypatch.setattr(service_migration.op, "get_bind", lambda: connection)
        monkeypatch.setattr(signal_migration.op, "get_bind", lambda: connection)
        service_migration.upgrade()
        connection.execute(
            fact_tables[1].insert(),
            {"id": "fact_website", "fact_key": "website_status"},
        )

        signal_migration.upgrade()
        signal_migration.upgrade()

        signal_count = connection.scalar(sa.select(sa.func.count()).select_from(signals))
        mapping_count = connection.scalar(sa.select(sa.func.count()).select_from(mappings))
        website_signal_id = connection.scalar(
            sa.select(signals.c.id).where(signals.c.key == "website_status")
        )
        linked_signal_id = connection.scalar(
            sa.select(fact_tables[1].c.signal_definition_id).where(
                fact_tables[1].c.id == "fact_website"
            )
        )
        enabled_service_count = connection.scalar(
            sa.select(sa.func.count(sa.distinct(mappings.c.service_definition_id)))
            .select_from(mappings.join(services, mappings.c.service_definition_id == services.c.id))
            .where(services.c.status == "active")
        )

    expected_signal_count = (
        len(signal_migration.INITIAL_SIGNALS)
        + len(signal_migration.WEBSITE_SIGNALS)
        + len(signal_migration.MULTILINGUAL_SIGNALS)
    )
    assert signal_count == expected_signal_count
    assert mapping_count == sum(len(service[-1]) for service in signal_migration.SERVICES)
    assert linked_signal_id == website_signal_id
    assert enabled_service_count == 6
