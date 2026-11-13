"""limit website-upgrade leads to measured website quality

Revision ID: 20261113_0091
Revises: 20261113_0090
Create Date: 2026-11-13

Page-element checks such as a contact or booking form remain diagnostic
attributes.  They are not reliable enough to qualify or label a customer-facing
lead because a bounded crawl can miss pages that exist.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261113_0091"
down_revision = "20261113_0090"
branch_labels = None
depends_on = None


WEBSITE_QUALITY_SIGNAL = "website_quality_score"
RETIRED_UPGRADE_SIGNALS = {
    "mobile_viewport_present",
    "quote_or_booking_form_present",
    "contact_form_present",
    "primary_cta_present",
    "click_to_call_present",
    "no_quote_flow",
    "no_contact_form",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    now = datetime.now(timezone.utc)
    metadata = sa.MetaData()

    if {
        "service_definitions",
        "service_signal_mappings",
        "signal_definitions",
    }.issubset(tables):
        services = sa.Table("service_definitions", metadata, autoload_with=bind)
        mappings = sa.Table("service_signal_mappings", metadata, autoload_with=bind)
        definitions = sa.Table("signal_definitions", metadata, autoload_with=bind)
        service = bind.execute(
            sa.select(services.c.id, services.c.version).where(
                services.c.key == "website_upgrade"
            )
        ).mappings().one_or_none()
        quality_signal_id = bind.scalar(
            sa.select(definitions.c.id).where(
                definitions.c.key == WEBSITE_QUALITY_SIGNAL
            )
        )
        if service is not None:
            bind.execute(
                mappings.delete().where(
                    mappings.c.service_definition_id == service["id"]
                )
            )
            if quality_signal_id is not None:
                bind.execute(
                    mappings.insert(),
                    {
                        "id": "mapping_website_upgrade_quality_only",
                        "service_definition_id": service["id"],
                        "signal_definition_id": quality_signal_id,
                        "weight": 1.0,
                        "sort_order": 1,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
            bind.execute(
                services.update()
                .where(services.c.id == service["id"])
                .values(
                    label="Website needs improvement",
                    description=(
                        "A verified website has a measured, below-threshold "
                        "website quality grade."
                    ),
                    version=(service["version"] or 0) + 1,
                    updated_at=now,
                )
            )

    if "territories" not in tables:
        return
    territories = sa.Table("territories", metadata, autoload_with=bind)
    results = (
        sa.Table("audience_results", metadata, autoload_with=bind)
        if "audience_results" in tables
        else None
    )

    for territory in bind.execute(sa.select(territories)).mappings():
        service_keys = list(territory.get("service_keys") or [])
        if "website_upgrade" not in service_keys:
            continue
        original_signals = list(territory.get("signal_keys") or [])
        managed = RETIRED_UPGRADE_SIGNALS | {WEBSITE_QUALITY_SIGNAL}
        signal_keys = [key for key in original_signals if key not in managed]
        signal_keys.append(WEBSITE_QUALITY_SIGNAL)
        signal_keys = list(dict.fromkeys(signal_keys))
        values = {
            "signal_keys": signal_keys,
            "updated_at": now,
        }
        if "criteria_version" in territories.c:
            values["criteria_version"] = int(territory.get("criteria_version") or 0) + 1
        bind.execute(
            territories.update()
            .where(territories.c.id == territory["id"])
            .values(**values)
        )

        if results is None:
            continue
        current_results = list(
            bind.execute(
                sa.select(results)
                .where(results.c.audience_id == territory["id"])
                .order_by(results.c.rank_position)
            ).mappings()
        )
        allowed = set(signal_keys)
        retained_ids = [
            row["id"]
            for row in current_results
            if _matched_signal_keys(row.get("match_snapshot")) & allowed
        ]
        removed_ids = [
            row["id"] for row in current_results if row["id"] not in retained_ids
        ]
        if removed_ids:
            bind.execute(results.delete().where(results.c.id.in_(removed_ids)))
        if retained_ids:
            bind.execute(
                results.update()
                .where(results.c.id.in_(retained_ids))
                .values(rank_position=-results.c.rank_position)
            )
            for rank, result_id in enumerate(retained_ids, start=1):
                bind.execute(
                    results.update()
                    .where(results.c.id == result_id)
                    .values(rank_position=rank, updated_at=now)
                )

        territory_values = {}
        if "match_result_count" in territories.c:
            territory_values["match_result_count"] = len(retained_ids)
        if "match_new_result_count" in territories.c:
            territory_values["match_new_result_count"] = 0
        if "match_state" in territories.c:
            territory_values["match_state"] = "partial"
        if "match_completed_at" in territories.c:
            territory_values["match_completed_at"] = now
        if "match_failure_reason" in territories.c:
            territory_values["match_failure_reason"] = None
        if territory_values:
            bind.execute(
                territories.update()
                .where(territories.c.id == territory["id"])
                .values(**territory_values)
            )


def _matched_signal_keys(snapshot: object) -> set[str]:
    if not isinstance(snapshot, dict):
        return set()
    raw = snapshot.get("raw")
    profile_match = raw.get("profile_match") if isinstance(raw, dict) else None
    matched = (
        profile_match.get("matched_signals")
        if isinstance(profile_match, dict)
        else None
    )
    if not isinstance(matched, list):
        return set()
    return {
        str(item.get("signal_key"))
        for item in matched
        if isinstance(item, dict) and item.get("signal_key")
    }


def downgrade() -> None:
    # Restoring shallow page-element checks as lead qualifiers would recreate
    # the false-positive behavior this migration removes.
    pass
