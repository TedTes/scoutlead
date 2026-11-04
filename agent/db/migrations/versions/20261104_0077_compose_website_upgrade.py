"""compose website upgrade from measured technical and conversion evidence

Revision ID: 20261104_0077
Revises: 20261103_0076
Create Date: 2026-11-04

Keep one customer-facing website-upgrade opportunity while restoring its
auditable component evidence. Page-level negatives still require the scoped
validation introduced before this migration; merely failing to find an element
on an unrelated page is not enough to publish a fact or qualify a lead.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261104_0077"
down_revision = "20261103_0076"
branch_labels = None
depends_on = None


WEBSITE_UPGRADE_SIGNALS = (
    ("website_quality_score", 0.45),
    ("mobile_viewport_present", 0.10),
    ("quote_or_booking_form_present", 0.15),
    ("contact_form_present", 0.15),
    ("primary_cta_present", 0.10),
    ("click_to_call_present", 0.05),
)
WEBSITE_SERVICE_SIGNALS = {
    "website_availability": ("website_status",),
    "website_upgrade": tuple(key for key, _ in WEBSITE_UPGRADE_SIGNALS),
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

    service = (
        bind.execute(
            sa.select(services.c.id, services.c.version).where(
                services.c.key == "website_upgrade"
            )
        )
        .mappings()
        .one_or_none()
    )
    if service is None:
        return

    definition_ids = dict(
        bind.execute(
            sa.select(definitions.c.key, definitions.c.id).where(
                definitions.c.key.in_(tuple(key for key, _ in WEBSITE_UPGRADE_SIGNALS))
            )
        ).all()
    )
    bind.execute(
        services.update()
        .where(services.c.id == service["id"])
        .values(
            label="Website needs improvement",
            description=(
                "A verified website has measured technical, mobile, or "
                "customer-conversion gaps."
            ),
            status="active",
            version=(service["version"] or 0) + 1,
            updated_at=now,
        )
    )
    bind.execute(
        mappings.delete().where(mappings.c.service_definition_id == service["id"])
    )
    rows = [
        {
            "id": f"mapping_website_composite_{index}",
            "service_definition_id": service["id"],
            "signal_definition_id": definition_ids[key],
            "weight": weight,
            "sort_order": index,
            "created_at": now,
            "updated_at": now,
        }
        for index, (key, weight) in enumerate(WEBSITE_UPGRADE_SIGNALS, start=1)
        if key in definition_ids
    ]
    if rows:
        bind.execute(mappings.insert(), rows)

    if inspector.has_table("territories"):
        territories = sa.Table("territories", metadata, autoload_with=bind)
        if {"service_keys", "signal_keys"}.issubset(territories.c.keys()):
            for row in bind.execute(
                sa.select(
                    territories.c.id,
                    territories.c.service_keys,
                    territories.c.signal_keys,
                )
            ).mappings():
                service_keys = list(row["service_keys"] or [])
                if not any(key in WEBSITE_SERVICE_SIGNALS for key in service_keys):
                    continue
                managed_keys = {
                    signal
                    for signals in WEBSITE_SERVICE_SIGNALS.values()
                    for signal in signals
                }
                signal_keys = [
                    key
                    for key in list(row["signal_keys"] or [])
                    if key not in managed_keys
                ]
                signal_keys.extend(
                    signal
                    for service_key in service_keys
                    for signal in WEBSITE_SERVICE_SIGNALS.get(service_key, ())
                )
                values = {
                    "signal_keys": list(dict.fromkeys(signal_keys)),
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
    # Removing component evidence would silently change saved-search meaning.
    pass
