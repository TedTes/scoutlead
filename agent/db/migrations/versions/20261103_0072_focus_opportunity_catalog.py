"""focus the customer-facing opportunity catalog

Revision ID: 20261103_0072
Revises: 20261102_0071
Create Date: 2026-11-03

Signal definitions are the observable business-attribute catalog.  Services are
the smaller set of opportunities a customer can select for an audience.  Keep
the evidence catalog intact, but expose only four evidence-backed opportunities.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261103_0072"
down_revision = "20261102_0071"
branch_labels = None
depends_on = None


OPPORTUNITIES: dict[str, dict] = {
    "website_availability": {
        "id": "service_website_availability",
        "label": "Website unavailable",
        "description": "No verified business website, or the known website is unavailable.",
        "sort_order": 10,
        "attributes": (("website_status", 1.0),),
    },
    "website_upgrade": {
        "id": "service_website_upgrade",
        "label": "Website needs upgrading",
        "description": (
            "A verified website has measurable security, mobile, quality, "
            "or usability gaps."
        ),
        "sort_order": 20,
        "attributes": (
            ("uses_https", 0.20),
            ("mobile_viewport_present", 0.15),
            ("website_quality_score", 0.20),
            ("performance_score", 0.20),
            ("accessibility_score", 0.10),
            ("best_practices_score", 0.15),
        ),
    },
    "lead_capture": {
        "id": "service_lead_capture",
        "label": "Lead-capture gap",
        "description": "The website is missing a clear inquiry, quote, call, or booking path.",
        "sort_order": 30,
        "attributes": (
            ("contact_form_present", 0.30),
            ("quote_or_booking_form_present", 0.30),
            ("primary_cta_present", 0.25),
            ("click_to_call_present", 0.15),
        ),
    },
    "reputation_trust": {
        "id": "service_reputation_trust",
        "label": "Reputation gap",
        "description": "The business has a clearly low public rating or too few public reviews.",
        "sort_order": 40,
        "attributes": (
            ("google_rating", 0.60),
            ("google_review_count", 0.40),
        ),
    },
}

RETIRED_OPPORTUNITIES = {
    "website_modernization",
    "booking_payments",
    "performance_accessibility",
    "local_visibility",
}

LEGACY_REPLACEMENTS = {
    "website_modernization": ("website_availability", "website_upgrade"),
    "booking_payments": ("lead_capture",),
    "performance_accessibility": ("website_upgrade",),
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    required = {
        "service_definitions",
        "service_signal_mappings",
        "signal_definitions",
    }
    if not all(inspector.has_table(table) for table in required):
        return

    metadata = sa.MetaData()
    services = sa.Table("service_definitions", metadata, autoload_with=bind)
    mappings = sa.Table("service_signal_mappings", metadata, autoload_with=bind)
    attributes = sa.Table("signal_definitions", metadata, autoload_with=bind)
    now = datetime.now(timezone.utc)

    service_ids = _upsert_opportunities(bind, services, now)
    attribute_ids = dict(bind.execute(sa.select(attributes.c.key, attributes.c.id)).all())
    _tune_attribute_thresholds(bind, attributes, now)
    _replace_mappings(bind, mappings, service_ids, attribute_ids, now)

    bind.execute(
        services.update()
        .where(services.c.key.in_(RETIRED_OPPORTUNITIES))
        .values(status="inactive", updated_at=now)
    )

    if inspector.has_table("territories"):
        territories = sa.Table("territories", metadata, autoload_with=bind)
        if "service_keys" in territories.c and "signal_keys" in territories.c:
            _migrate_audiences(
                bind,
                territories,
                now,
            )


def downgrade() -> None:
    # Restoring the broad catalog would re-expose weak or non-sellable signals.
    pass


def _upsert_opportunities(bind, services, now) -> dict[str, str]:
    rows = {
        row.key: row
        for row in bind.execute(
            sa.select(services.c.key, services.c.id, services.c.version)
        )
    }
    service_ids: dict[str, str] = {}
    for key, definition in OPPORTUNITIES.items():
        existing = rows.get(key)
        values = {
            "label": definition["label"],
            "description": definition["description"],
            "status": "active",
            "sort_order": definition["sort_order"],
            "updated_at": now,
        }
        if existing is None:
            service_id = definition["id"]
            bind.execute(
                services.insert().values(
                    id=service_id,
                    key=key,
                    version=1,
                    created_at=now,
                    **values,
                )
            )
        else:
            service_id = str(existing.id)
            bind.execute(
                services.update()
                .where(services.c.id == existing.id)
                .values(version=(existing.version or 0) + 1, **values)
            )
        service_ids[key] = service_id
    return service_ids


def _replace_mappings(bind, mappings, service_ids, attribute_ids, now) -> None:
    for service_key, definition in OPPORTUNITIES.items():
        service_id = service_ids.get(service_key)
        if service_id is None:
            continue
        bind.execute(
            mappings.delete().where(mappings.c.service_definition_id == service_id)
        )
        rows = [
            {
                "id": f"mapping_focus_{service_key}_{index + 1}",
                "service_definition_id": service_id,
                "signal_definition_id": attribute_ids[attribute_key],
                "weight": weight,
                "sort_order": index,
                "created_at": now,
                "updated_at": now,
            }
            for index, (attribute_key, weight) in enumerate(definition["attributes"])
            if attribute_key in attribute_ids
        ]
        if rows:
            bind.execute(mappings.insert(), rows)


def _tune_attribute_thresholds(bind, attributes, now) -> None:
    if not {"config", "version", "updated_at"}.issubset(attributes.c.keys()):
        return
    focused_config = {
        # Excludes "thin" (55) while retaining unreachable, parked,
        # unavailable, and verified missing states. "not_listed" remains
        # unknown and never receives an attribute score.
        "website_status": {"audience_min_score": 70},
        # A 4.3 listing is not a sellable reputation problem. Only ratings
        # clearly below 4.0 qualify.
        "google_rating": {"opportunity_threshold": 4.0},
        "google_review_count": {"opportunity_threshold": 15},
    }
    rows = bind.execute(
        sa.select(attributes.c.id, attributes.c.key, attributes.c.config).where(
            attributes.c.key.in_(focused_config)
        )
    ).mappings()
    for row in rows:
        config = dict(row["config"] or {})
        config.update(focused_config[row["key"]])
        bind.execute(
            attributes.update()
            .where(attributes.c.id == row["id"])
            .values(
                config=config,
                version=attributes.c.version + 1,
                updated_at=now,
            )
        )


def _migrate_audiences(
    bind,
    territories,
    now,
) -> None:
    for row in bind.execute(
        sa.select(
            territories.c.id,
            territories.c.service_keys,
            territories.c.signal_keys,
        )
    ).mappings():
        original_services = list(row["service_keys"] or [])
        migrated_services: list[str] = []
        changed = False
        for service_key in original_services:
            replacements = LEGACY_REPLACEMENTS.get(service_key)
            if replacements is None:
                migrated_services.append(service_key)
                continue
            migrated_services.extend(replacements)
            changed = True
        if not changed:
            continue
        migrated_services = list(dict.fromkeys(migrated_services))
        signal_keys = list(dict.fromkeys(
            attribute_key
            for service_key in migrated_services
            for attribute_key, _ in OPPORTUNITIES.get(service_key, {}).get(
                "attributes", ()
            )
        ))
        bind.execute(
            territories.update()
            .where(territories.c.id == row["id"])
            .values(
                service_keys=migrated_services,
                signal_keys=signal_keys or list(row["signal_keys"] or []),
                updated_at=now,
            )
        )
