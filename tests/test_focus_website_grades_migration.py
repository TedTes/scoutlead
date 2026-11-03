from importlib import import_module

import sqlalchemy as sa


def test_focus_website_grades_narrows_catalog_and_stages_page_absence(
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
    facts = sa.Table(
        "business_facts",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("fact_key", sa.String, nullable=False),
        sa.Column("quality_state", sa.String, nullable=False),
        sa.Column("resolution_state", sa.String, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
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
        "db.migrations.versions.20261103_0076_focus_website_grades"
    )
    now = migration.datetime.now(migration.timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            services.insert(),
            [
                {
                    "id": f"service_{key}",
                    "key": key,
                    "label": key,
                    "description": key,
                    "status": "active",
                    "sort_order": index,
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
                for index, key in enumerate(
                    ["website_availability", "website_upgrade", "lead_capture"]
                )
            ],
        )
        connection.execute(
            definitions.insert(),
            [
                {"id": "signal_website_status", "key": "website_status"},
                {
                    "id": "signal_website_quality_score",
                    "key": "website_quality_score",
                },
                {
                    "id": "signal_contact_form_present",
                    "key": "contact_form_present",
                },
            ],
        )
        connection.execute(
            mappings.insert(),
            {
                "id": "mapping_old_contact",
                "service_definition_id": "service_lead_capture",
                "signal_definition_id": "signal_contact_form_present",
                "weight": 1.0,
                "sort_order": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            facts.insert(),
            {
                "id": "fact_contact",
                "fact_key": "contact_form_present",
                "quality_state": "published",
                "resolution_state": "confirmed",
                "expires_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory_old",
                "service_keys": ["lead_capture"],
                "signal_keys": ["contact_form_present"],
                "criteria_version": 3,
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
        assert active == {"website_availability", "website_upgrade"}
        labels = {
            row["key"]: row["label"]
            for row in connection.execute(
                sa.select(services.c.key, services.c.label)
            ).mappings()
        }
        assert labels["website_availability"] == "Website missing"
        assert labels["website_upgrade"] == "Website needs upgrade"
        mapped = set(
            connection.scalars(
                sa.select(definitions.c.key).join(
                    mappings,
                    mappings.c.signal_definition_id == definitions.c.id,
                )
            )
        )
        assert mapped == {"website_status", "website_quality_score"}
        page_fact = connection.execute(sa.select(facts)).mappings().one()
        assert page_fact["quality_state"] == "staged"
        assert page_fact["resolution_state"] == "stale"
        audience = connection.execute(sa.select(territories)).mappings().one()
        assert audience["service_keys"] == ["website_upgrade"]
        assert audience["signal_keys"] == ["website_quality_score"]
        assert audience["criteria_version"] == 4
