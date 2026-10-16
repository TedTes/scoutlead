"""repair missing signal catalog and service mappings

Revision ID: 20261016_0053
Revises: 20261015_0052
Create Date: 2026-10-16
"""

from datetime import datetime, timezone
from importlib import import_module

from alembic import op
import sqlalchemy as sa


revision = "20261016_0053"
down_revision = "20261015_0052"
branch_labels = None
depends_on = None


INITIAL_SIGNALS = import_module(
    "db.migrations.versions.20261012_0041_signal_definitions"
).INITIAL_SIGNALS
WEBSITE_SIGNALS = import_module(
    "db.migrations.versions.20261012_0043_website_quality_signals"
).WEBSITE_SIGNALS
MULTILINGUAL_SIGNALS = import_module(
    "db.migrations.versions.20261013_0044_service_definitions"
).MULTILINGUAL_SIGNALS
SERVICES = import_module(
    "db.migrations.versions.20261015_0052_repair_service_catalog"
).SERVICES


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    signals = _signal_table()
    existing_signal_keys = set(bind.execute(sa.select(signals.c.key)).scalars())
    signal_rows = [
        *_signal_rows(INITIAL_SIGNALS, now, auto_publish=True),
        *_signal_rows(WEBSITE_SIGNALS, now, auto_publish=True),
        *_multilingual_signal_rows(now),
    ]
    missing_signals = [
        row for row in signal_rows if row["key"] not in existing_signal_keys
    ]
    if missing_signals:
        bind.execute(signals.insert(), missing_signals)

    signal_ids = dict(bind.execute(sa.select(signals.c.key, signals.c.id)).all())
    for signal_key, signal_id in signal_ids.items():
        for table_name in ("fact_claims", "business_facts"):
            bind.execute(
                sa.text(
                    f"UPDATE {table_name} SET signal_definition_id = :signal_id "
                    "WHERE fact_key = :fact_key AND signal_definition_id IS NULL"
                ),
                {"signal_id": signal_id, "fact_key": signal_key},
            )

    services = sa.table(
        "service_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
    )
    service_ids = dict(bind.execute(sa.select(services.c.key, services.c.id)).all())
    mappings = _mapping_table()
    existing_mappings = set(
        bind.execute(
            sa.select(mappings.c.service_definition_id, mappings.c.signal_definition_id)
        ).all()
    )
    missing_mappings = []
    for _, service_key, _, _, _, signal_keys in SERVICES:
        service_id = service_ids.get(service_key)
        if service_id is None:
            continue
        for index, signal_key in enumerate(signal_keys):
            signal_id = signal_ids.get(signal_key)
            if signal_id is None or (service_id, signal_id) in existing_mappings:
                continue
            missing_mappings.append(
                {
                    "id": f"mapping_repair_{service_key}_{index + 1}",
                    "service_definition_id": service_id,
                    "signal_definition_id": signal_id,
                    "weight": 1.0,
                    "sort_order": index,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if missing_mappings:
        bind.execute(mappings.insert(), missing_mappings)


def downgrade() -> None:
    # The repaired rows may be referenced immediately by collected facts and
    # saved audience profiles, so rolling back must not delete catalog data.
    pass


def _signal_rows(definitions, now, *, auto_publish: bool) -> list[dict]:
    return [
        {
            "id": signal_id,
            "key": key,
            "label": label,
            "description": None,
            "value_type": value_type,
            "category": category,
            "unit": unit,
            "status": "active",
            "collector_key": collector,
            "extractor_key": extractor,
            "freshness_days": freshness_days,
            "opportunity_direction": direction,
            "config": {**config, "auto_publish": auto_publish, "confidence": 100},
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        for (
            signal_id,
            key,
            label,
            value_type,
            category,
            unit,
            collector,
            extractor,
            freshness_days,
            direction,
            config,
        ) in definitions
    ]


def _multilingual_signal_rows(now) -> list[dict]:
    return [
        {
            "id": signal_id,
            "key": key,
            "label": label,
            "description": None,
            "value_type": value_type,
            "category": category,
            "unit": unit,
            "status": "active",
            "collector_key": collector,
            "extractor_key": extractor,
            "freshness_days": 30,
            "opportunity_direction": direction,
            "config": {
                **config,
                "confidence": 100,
                "requires_validation": True,
            },
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        for (
            signal_id,
            key,
            label,
            value_type,
            category,
            unit,
            collector,
            extractor,
            direction,
            config,
        ) in MULTILINGUAL_SIGNALS
    ]


def _signal_table():
    return sa.table(
        "signal_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("value_type", sa.String),
        sa.column("category", sa.String),
        sa.column("unit", sa.String),
        sa.column("status", sa.String),
        sa.column("collector_key", sa.String),
        sa.column("extractor_key", sa.String),
        sa.column("freshness_days", sa.Integer),
        sa.column("opportunity_direction", sa.String),
        sa.column("config", sa.JSON),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _mapping_table():
    return sa.table(
        "service_signal_mappings",
        sa.column("id", sa.String),
        sa.column("service_definition_id", sa.String),
        sa.column("signal_definition_id", sa.String),
        sa.column("weight", sa.Float),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
