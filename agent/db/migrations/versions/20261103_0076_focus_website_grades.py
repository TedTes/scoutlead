"""focus lead matching on website availability and website grade

Revision ID: 20261103_0076
Revises: 20261103_0075
Create Date: 2026-11-03

Granular page checks remain business attributes for audit and grade evidence,
but they no longer independently qualify an audience or select an outreach
claim. Existing page-negative facts are staged for scoped reinspection.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261103_0076"
down_revision = "20261103_0075"
branch_labels = None
depends_on = None

ACTIVE_SERVICES = {
    "website_availability": {
        "label": "Website missing",
        "description": (
            "Completed verification did not find a matching business website."
        ),
        "signals": (("website_status", 1.0),),
    },
    "website_upgrade": {
        "label": "Website needs upgrade",
        "description": (
            "A verified website has a sufficiently measured, below-threshold "
            "website quality grade."
        ),
        "signals": (("website_quality_score", 1.0),),
    },
}
PAGE_SCOPED_KEYS = {
    "contact_form_present",
    "quote_or_booking_form_present",
    "primary_cta_present",
    "click_to_call_present",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    required = {
        "service_definitions",
        "service_signal_mappings",
        "signal_definitions",
    }
    if not all(inspector.has_table(name) for name in required):
        return

    metadata = sa.MetaData()
    services = sa.Table("service_definitions", metadata, autoload_with=bind)
    mappings = sa.Table("service_signal_mappings", metadata, autoload_with=bind)
    definitions = sa.Table("signal_definitions", metadata, autoload_with=bind)
    now = datetime.now(timezone.utc)

    bind.execute(
        services.update()
        .where(~services.c.key.in_(tuple(ACTIVE_SERVICES)))
        .values(status="inactive", updated_at=now)
    )
    bind.execute(
        mappings.delete().where(
            mappings.c.service_definition_id.in_(
                sa.select(services.c.id).where(
                    ~services.c.key.in_(tuple(ACTIVE_SERVICES))
                )
            )
        )
    )
    service_rows = {
        row.key: row
        for row in bind.execute(
            sa.select(services.c.id, services.c.key, services.c.version).where(
                services.c.key.in_(tuple(ACTIVE_SERVICES))
            )
        )
    }
    definition_ids = dict(
        bind.execute(sa.select(definitions.c.key, definitions.c.id)).all()
    )
    for sort_order, (service_key, config) in enumerate(
        ACTIVE_SERVICES.items(), start=1
    ):
        row = service_rows.get(service_key)
        if row is None:
            continue
        bind.execute(
            services.update()
            .where(services.c.id == row.id)
            .values(
                label=config["label"],
                description=config["description"],
                status="active",
                sort_order=sort_order * 10,
                version=(row.version or 0) + 1,
                updated_at=now,
            )
        )
        bind.execute(
            mappings.delete().where(mappings.c.service_definition_id == row.id)
        )
        mapping_rows = [
            {
                "id": f"mapping_website_grade_{service_key}_{index}",
                "service_definition_id": row.id,
                "signal_definition_id": definition_ids[signal_key],
                "weight": weight,
                "sort_order": index,
                "created_at": now,
                "updated_at": now,
            }
            for index, (signal_key, weight) in enumerate(config["signals"], start=1)
            if signal_key in definition_ids
        ]
        if mapping_rows:
            bind.execute(mappings.insert(), mapping_rows)

    if inspector.has_table("business_facts"):
        facts = sa.Table("business_facts", metadata, autoload_with=bind)
        bind.execute(
            facts.update()
            .where(facts.c.fact_key.in_(PAGE_SCOPED_KEYS))
            .values(
                quality_state="staged",
                resolution_state="stale",
                expires_at=now,
                updated_at=now,
            )
        )

    if inspector.has_table("territories"):
        territories = sa.Table("territories", metadata, autoload_with=bind)
        if {"service_keys", "signal_keys"}.issubset(territories.c.keys()):
            rows = bind.execute(
                sa.select(
                    territories.c.id,
                    territories.c.service_keys,
                    territories.c.signal_keys,
                )
            ).mappings()
            for row in rows:
                original_services = list(row["service_keys"] or [])
                if not original_services:
                    continue
                services_for_profile = [
                    key for key in original_services if key in ACTIVE_SERVICES
                ]
                if any(key not in ACTIVE_SERVICES for key in original_services):
                    services_for_profile.append("website_upgrade")
                services_for_profile = list(dict.fromkeys(services_for_profile))
                signal_keys = list(
                    dict.fromkeys(
                        signal_key
                        for service_key in services_for_profile
                        for signal_key, _ in ACTIVE_SERVICES[service_key]["signals"]
                    )
                )
                values = {
                    "service_keys": services_for_profile,
                    "signal_keys": signal_keys,
                    "updated_at": now,
                }
                if "criteria_version" in territories.c:
                    values["criteria_version"] = territories.c.criteria_version + 1
                bind.execute(
                    territories.update()
                    .where(territories.c.id == row["id"])
                    .values(**values)
                )


def downgrade() -> None:
    # Restoring broad, page-element opportunities would requalify leads from
    # evidence that this migration intentionally marked unsafe.
    pass
