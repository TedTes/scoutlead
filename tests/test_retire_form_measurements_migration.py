from importlib import import_module

import sqlalchemy as sa


def test_migration_retires_form_measurements_and_removes_legacy_results(monkeypatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("status", sa.String),
        sa.Column("collector_key", sa.String),
        sa.Column("extractor_key", sa.String),
        sa.Column("opportunity_direction", sa.String),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    mappings = sa.Table(
        "service_signal_mappings",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("signal_definition_id", sa.String, nullable=False),
    )
    attributes = sa.Table(
        "business_attributes",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("row_type", sa.String, nullable=False),
        sa.Column("attribute_key", sa.String),
    )
    territories = sa.Table(
        "territories",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("signal_keys", sa.JSON, nullable=False),
        sa.Column("criteria_version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    results = sa.Table(
        "audience_results",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("match_snapshot", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    metadata.create_all(engine)
    migration = import_module(
        "db.migrations.versions.20261113_0092_retire_form_measurements"
    )
    now = migration.datetime.now(migration.timezone.utc)

    def snapshot(*signals: dict) -> dict:
        return {
            "raw": {
                "profile_match": {
                    "matched_signal_count": len(signals),
                    "confirmed_signal_count": len(signals),
                    "matched_signals": list(signals),
                    "signals": {
                        item["signal_key"]: {"matched": True}
                        for item in signals
                    },
                }
            }
        }

    with engine.begin() as connection:
        connection.execute(
            definitions.insert(),
            [
                {
                    "id": "contact",
                    "key": "contact_form_present",
                    "status": "active",
                    "collector_key": "website_http",
                    "extractor_key": "contact_form",
                    "opportunity_direction": "false_is_opportunity",
                    "updated_at": now,
                },
                {
                    "id": "quote",
                    "key": "quote_or_booking_form_present",
                    "status": "active",
                    "collector_key": "website_http",
                    "extractor_key": "quote_form",
                    "opportunity_direction": "false_is_opportunity",
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            mappings.insert(),
            [
                {"id": "m1", "signal_definition_id": "contact"},
                {"id": "m2", "signal_definition_id": "quote"},
            ],
        )
        connection.execute(
            attributes.insert(),
            [
                {
                    "id": "canonical_form",
                    "row_type": "attribute",
                    "attribute_key": "contact_form_present",
                },
                {
                    "id": "raw_evidence",
                    "row_type": "evidence",
                    "attribute_key": None,
                },
            ],
        )
        connection.execute(
            territories.insert(),
            {
                "id": "territory",
                "signal_keys": ["no_contact_form", "website_quality_score"],
                "criteria_version": 2,
                "updated_at": now,
            },
        )
        connection.execute(
            results.insert(),
            [
                {
                    "id": "form_only",
                    "match_snapshot": snapshot(
                        {
                            "signal_key": "no_quote_flow",
                            "attribute_key": "quote_or_booking_form_present",
                            "confidence": "confirmed",
                        }
                    ),
                    "updated_at": now,
                },
                {
                    "id": "mixed",
                    "match_snapshot": snapshot(
                        {
                            "signal_key": "contact_form_present",
                            "attribute_key": "contact_form_present",
                            "confidence": "confirmed",
                        },
                        {
                            "signal_key": "website_quality_score",
                            "attribute_key": "website_quality_score",
                            "confidence": "confirmed",
                        },
                    ),
                    "updated_at": now,
                },
            ],
        )

        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        retired = connection.execute(sa.select(definitions)).mappings().all()
        assert all(row["status"] == "retired" for row in retired)
        assert all(row["collector_key"] is None for row in retired)
        assert connection.scalar(sa.select(sa.func.count()).select_from(mappings)) == 0
        assert connection.scalars(sa.select(attributes.c.id)).all() == ["raw_evidence"]
        territory = connection.execute(sa.select(territories)).mappings().one()
        assert territory["signal_keys"] == ["website_quality_score"]
        assert territory["criteria_version"] == 3
        remaining = connection.execute(sa.select(results)).mappings().one()
        assert remaining["id"] == "mixed"
        profile_match = remaining["match_snapshot"]["raw"]["profile_match"]
        assert [
            item["signal_key"] for item in profile_match["matched_signals"]
        ] == ["website_quality_score"]
        assert profile_match["matched_signal_count"] == 1

