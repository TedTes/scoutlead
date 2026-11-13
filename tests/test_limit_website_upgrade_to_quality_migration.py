from importlib import import_module

import sqlalchemy as sa


def test_migration_removes_page_checks_and_prunes_old_results(monkeypatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    services = sa.Table(
        "service_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False),
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
        sa.Column("match_result_count", sa.Integer, nullable=False),
        sa.Column("match_new_result_count", sa.Integer, nullable=False),
        sa.Column("match_state", sa.String, nullable=False),
        sa.Column("match_completed_at", sa.DateTime(timezone=True)),
        sa.Column("match_failure_reason", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    results = sa.Table(
        "audience_results",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("audience_id", sa.String, nullable=False),
        sa.Column("rank_position", sa.Integer, nullable=False),
        sa.Column("match_snapshot", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("audience_id", "rank_position"),
    )
    metadata.create_all(engine)
    migration = import_module(
        "db.migrations.versions.20261113_0091_limit_website_upgrade_to_quality"
    )
    now = migration.datetime.now(migration.timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            services.insert(),
            {
                "id": "service_upgrade",
                "key": "website_upgrade",
                "label": "Website needs improvement",
                "description": "old composite",
                "version": 3,
                "updated_at": now,
            },
        )
        connection.execute(
            definitions.insert(),
            [
                {"id": "signal_quality", "key": "website_quality_score"},
                {"id": "signal_form", "key": "contact_form_present"},
            ],
        )
        connection.execute(
            mappings.insert(),
            [
                {
                    "id": "mapping_quality",
                    "service_definition_id": "service_upgrade",
                    "signal_definition_id": "signal_quality",
                    "weight": 0.5,
                    "sort_order": 1,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "mapping_form",
                    "service_definition_id": "service_upgrade",
                    "signal_definition_id": "signal_form",
                    "weight": 0.5,
                    "sort_order": 2,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory_upgrade",
                "service_keys": ["website_upgrade"],
                "signal_keys": [
                    "website_quality_score",
                    "contact_form_present",
                    "quote_or_booking_form_present",
                ],
                "criteria_version": 7,
                "match_result_count": 2,
                "match_new_result_count": 2,
                "match_state": "ready",
                "match_failure_reason": None,
                "updated_at": now,
            },
        )

        def snapshot(signal_key: str) -> dict:
            return {
                "raw": {
                    "profile_match": {
                        "matched_signals": [{"signal_key": signal_key}]
                    }
                }
            }

        connection.execute(
            results.insert(),
            [
                {
                    "id": "result_form",
                    "audience_id": "territory_upgrade",
                    "rank_position": 1,
                    "match_snapshot": snapshot("contact_form_present"),
                    "updated_at": now,
                },
                {
                    "id": "result_quality",
                    "audience_id": "territory_upgrade",
                    "rank_position": 2,
                    "match_snapshot": snapshot("website_quality_score"),
                    "updated_at": now,
                },
            ],
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        mapped_keys = connection.scalars(
            sa.select(definitions.c.key)
            .join(mappings, mappings.c.signal_definition_id == definitions.c.id)
            .where(mappings.c.service_definition_id == "service_upgrade")
        ).all()
        assert mapped_keys == ["website_quality_score"]

        territory = connection.execute(sa.select(territories)).mappings().one()
        assert territory["signal_keys"] == ["website_quality_score"]
        assert territory["criteria_version"] == 8
        assert territory["match_result_count"] == 1
        assert territory["match_state"] == "partial"

        remaining = connection.execute(sa.select(results)).mappings().one()
        assert remaining["id"] == "result_quality"
        assert remaining["rank_position"] == 1
