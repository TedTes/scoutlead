from importlib import import_module

import sqlalchemy as sa


def test_focus_opportunity_catalog_preserves_attributes_and_migrates_audiences(
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
        sa.Column("sort_order", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    attributes = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)

    migration = import_module(
        "db.migrations.versions.20261103_0072_focus_opportunity_catalog"
    )
    now = migration.datetime.now(migration.timezone.utc)
    all_attributes = {
        key
        for definition in migration.OPPORTUNITIES.values()
        for key, _ in definition["attributes"]
    }
    with engine.begin() as connection:
        connection.execute(
            services.insert(),
            [
                {
                    "id": f"service_{key}",
                    "key": key,
                    "label": key,
                    "description": None,
                    "status": "active",
                    "sort_order": index,
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                for index, key in enumerate(
                    [
                        "website_modernization",
                        "lead_capture",
                        "booking_payments",
                        "performance_accessibility",
                        "local_visibility",
                        "reputation_trust",
                    ]
                )
            ],
        )
        connection.execute(
            attributes.insert(),
            [
                {
                    "id": f"attribute_{key}",
                    "key": key,
                    "config": {},
                    "version": 1,
                    "updated_at": now,
                }
                for key in all_attributes
            ],
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory_legacy",
                "service_keys": [
                    "website_modernization",
                    "booking_payments",
                    "performance_accessibility",
                ],
                "signal_keys": ["obsolete_signal"],
                "updated_at": now,
            },
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        active = set(
            connection.scalars(
                sa.select(services.c.key).where(services.c.status == "active")
            )
        )
        assert active == set(migration.OPPORTUNITIES)
        audience = connection.execute(
            sa.select(territories).where(territories.c.id == "territory_legacy")
        ).mappings().one()
        assert audience["service_keys"] == [
            "website_availability",
            "website_upgrade",
            "lead_capture",
        ]
        assert set(audience["signal_keys"]) == {
            key
            for service_key in audience["service_keys"]
            for key, _ in migration.OPPORTUNITIES[service_key]["attributes"]
        }
        website_availability_id = connection.scalar(
            sa.select(services.c.id).where(
                services.c.key == "website_availability"
            )
        )
        mapped = set(
            connection.scalars(
                sa.select(attributes.c.key)
                .join(
                    mappings,
                    mappings.c.signal_definition_id == attributes.c.id,
                )
                .where(
                    mappings.c.service_definition_id == website_availability_id
                )
            )
        )
        assert mapped == {"website_status"}
        website_status_config = connection.scalar(
            sa.select(attributes.c.config).where(
                attributes.c.key == "website_status"
            )
        )
        assert website_status_config["audience_min_score"] == 70
        rating_config = connection.scalar(
            sa.select(attributes.c.config).where(
                attributes.c.key == "google_rating"
            )
        )
        assert rating_config["opportunity_threshold"] == 4.0

