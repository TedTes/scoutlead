from __future__ import annotations

import importlib

import sqlalchemy as sa


def test_retire_shallow_website_attributes_removes_rows_and_retires_definitions(
    monkeypatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    attributes = sa.Table(
        "business_attributes",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("attribute_key", sa.String, nullable=False),
    )
    definitions = sa.Table(
        "signal_definitions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("key", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261113_0097_retire_shallow_website_attributes"
    )

    with engine.begin() as connection:
        connection.execute(
            attributes.insert(),
            [
                {"id": "retired", "attribute_key": "contact_form_present"},
                {"id": "kept", "attribute_key": "website_quality_score"},
            ],
        )
        connection.execute(
            definitions.insert(),
            [
                {
                    "id": "retired",
                    "key": "contact_form_present",
                    "status": "active",
                },
                {
                    "id": "kept",
                    "key": "website_quality_score",
                    "status": "active",
                },
            ],
        )
        monkeypatch.setattr(migration.op, "get_bind", lambda: connection)
        migration.upgrade()

        assert connection.execute(
            sa.select(attributes.c.attribute_key)
        ).scalars().all() == ["website_quality_score"]
        assert dict(
            connection.execute(
                sa.select(definitions.c.key, definitions.c.status)
            ).all()
        ) == {
            "contact_form_present": "retired",
            "website_quality_score": "active",
        }
