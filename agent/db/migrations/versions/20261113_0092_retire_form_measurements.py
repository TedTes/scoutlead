"""retire contact and booking form measurements

Revision ID: 20261113_0092
Revises: 20261113_0091
Create Date: 2026-11-13

Bounded crawls cannot prove that a contact, quote, or booking form is absent.
These attributes are therefore removed from collection as well as matching.
Contact URLs discovered independently remain available for outreach routing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261113_0092"
down_revision = "20261113_0091"
branch_labels = None
depends_on = None


RETIRED_FORM_ATTRIBUTES = (
    "contact_form_present",
    "quote_or_booking_form_present",
)
RETIRED_FORM_SIGNALS = frozenset(
    {
        *RETIRED_FORM_ATTRIBUTES,
        "no_contact_form",
        "no_quote_flow",
    }
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    metadata = sa.MetaData()
    now = datetime.now(timezone.utc)

    definitions = None
    definition_ids: list[str] = []
    if "signal_definitions" in tables:
        definitions = sa.Table(
            "signal_definitions", metadata, autoload_with=bind
        )
        definition_ids = list(
            bind.scalars(
                sa.select(definitions.c.id).where(
                    definitions.c.key.in_(RETIRED_FORM_ATTRIBUTES)
                )
            )
        )

    if definition_ids and "service_signal_mappings" in tables:
        mappings = sa.Table(
            "service_signal_mappings", metadata, autoload_with=bind
        )
        bind.execute(
            mappings.delete().where(
                mappings.c.signal_definition_id.in_(definition_ids)
            )
        )

    if definitions is not None:
        bind.execute(
            definitions.update()
            .where(definitions.c.key.in_(RETIRED_FORM_ATTRIBUTES))
            .values(
                status="retired",
                collector_key=None,
                extractor_key=None,
                opportunity_direction="none",
                updated_at=now,
            )
        )

    if "business_attributes" in tables:
        attributes = sa.Table(
            "business_attributes", metadata, autoload_with=bind
        )
        bind.execute(
            attributes.delete().where(
                attributes.c.row_type == "attribute",
                attributes.c.attribute_key.in_(RETIRED_FORM_ATTRIBUTES),
            )
        )

    if "territories" in tables:
        territories = sa.Table("territories", metadata, autoload_with=bind)
        for territory in bind.execute(sa.select(territories)).mappings():
            current = list(territory.get("signal_keys") or [])
            cleaned = [
                key for key in current if key not in RETIRED_FORM_SIGNALS
            ]
            if cleaned == current:
                continue
            values: dict[str, object] = {
                "signal_keys": cleaned,
                "updated_at": now,
            }
            if "criteria_version" in territories.c:
                values["criteria_version"] = int(
                    territory.get("criteria_version") or 0
                ) + 1
            bind.execute(
                territories.update()
                .where(territories.c.id == territory["id"])
                .values(**values)
            )

    if "audience_results" in tables:
        results = sa.Table("audience_results", metadata, autoload_with=bind)
        for result in bind.execute(sa.select(results)).mappings():
            snapshot, remaining = _without_form_measurements(
                result.get("match_snapshot")
            )
            if remaining is None:
                continue
            if remaining == 0:
                bind.execute(results.delete().where(results.c.id == result["id"]))
                continue
            bind.execute(
                results.update()
                .where(results.c.id == result["id"])
                .values(match_snapshot=snapshot, updated_at=now)
            )


def _without_form_measurements(snapshot: object) -> tuple[object, int | None]:
    if not isinstance(snapshot, dict):
        return snapshot, None
    cleaned = dict(snapshot)
    raw = cleaned.get("raw")
    if not isinstance(raw, dict):
        return cleaned, None
    raw = dict(raw)
    profile_match = raw.get("profile_match")
    if not isinstance(profile_match, dict):
        return cleaned, None
    profile_match = dict(profile_match)
    matched = profile_match.get("matched_signals")
    if not isinstance(matched, list):
        return cleaned, None
    has_retired = any(
        isinstance(item, dict)
        and (
            str(item.get("signal_key") or "") in RETIRED_FORM_SIGNALS
            or str(item.get("attribute_key") or "") in RETIRED_FORM_ATTRIBUTES
        )
        for item in matched
    )
    if not has_retired:
        return cleaned, None
    retained = [
        item
        for item in matched
        if isinstance(item, dict)
        and str(item.get("signal_key") or "") not in RETIRED_FORM_SIGNALS
        and str(item.get("attribute_key") or "") not in RETIRED_FORM_ATTRIBUTES
    ]
    signals = profile_match.get("signals")
    if isinstance(signals, dict):
        profile_match["signals"] = {
            key: value
            for key, value in signals.items()
            if key not in RETIRED_FORM_SIGNALS
        }
    profile_match["matched_signals"] = retained
    if "matched_signal_count" in profile_match:
        profile_match["matched_signal_count"] = len(retained)
    if "confirmed_signal_count" in profile_match:
        profile_match["confirmed_signal_count"] = sum(
            item.get("confidence") == "confirmed" for item in retained
        )
    raw["profile_match"] = profile_match
    cleaned["raw"] = raw
    return cleaned, len(retained)


def downgrade() -> None:
    # Restoring unreliable absence measurements would recreate the behavior
    # intentionally removed by this migration.
    pass
