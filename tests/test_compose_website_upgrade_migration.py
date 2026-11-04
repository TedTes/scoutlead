from importlib import import_module

import sqlalchemy as sa


def test_compose_website_upgrade_restores_component_mappings_and_profiles(
    monkeypatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    services = sa.Table(
        "service_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
    )
    mappings = sa.Table(
        "service_signal_mappings",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("service_definition_id", sa.String, nullable=False),
        sa.Column("signal_definition_id", sa.String, nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    territories = sa.Table(
        "territories",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("service_keys", sa.JSON, nullable=False),
        sa.Column("signal_keys", sa.JSON, nullable=False),
        sa.Column("criteria_version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)

    migration = import_module(
        "db.migrations.versions.20261104_0077_compose_website_upgrade"
    )
    now = migration.datetime.now(migration.timezone.utc)
    signal_keys = [
        "website_status",
        *[key for key, _ in migration.WEBSITE_UPGRADE_SIGNALS],
    ]
    with engine.begin() as connection:
        connection.execute(
            services.insert(),
            [
                {
                    "id": "service_website_availability",
                    "key": "website_availability",
                    "label": "Website missing",
                    "description": "missing",
                    "status": "active",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "service_website_upgrade",
                    "key": "website_upgrade",
                    "label": "Website needs upgrade",
                    "description": "grade only",
                    "status": "active",
                    "version": 2,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            definitions.insert(),
            [{"id": f"signal_{key}", "key": key} for key in signal_keys],
        )
        connection.execute(
            mappings.insert(),
            {
                "id": "mapping_grade_only",
                "service_definition_id": "service_website_upgrade",
                "signal_definition_id": "signal_website_quality_score",
                "weight": 1.0,
                "sort_order": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory_upgrade",
                "service_keys": ["website_upgrade"],
                "signal_keys": ["website_quality_score"],
                "criteria_version": 4,
                "updated_at": now,
            },
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        mapped = connection.execute(
            sa.select(definitions.c.key, mappings.c.weight)
            .join(mappings, mappings.c.signal_definition_id == definitions.c.id)
            .where(mappings.c.service_definition_id == "service_website_upgrade")
            .order_by(mappings.c.sort_order)
        ).all()
        assert mapped == list(migration.WEBSITE_UPGRADE_SIGNALS)

        service = (
            connection.execute(
                sa.select(services).where(services.c.key == "website_upgrade")
            )
            .mappings()
            .one()
        )
        assert service["label"] == "Website needs improvement"
        assert service["version"] == 3
        assert "conversion" in service["description"]

        territory = connection.execute(sa.select(territories)).mappings().one()
        assert territory["signal_keys"] == [
            key for key, _ in migration.WEBSITE_UPGRADE_SIGNALS
        ]
        assert territory["criteria_version"] == 5
