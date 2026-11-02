"""quarantine map entities that were imported as businesses

Revision ID: 20261102_0069
Revises: 20261101_0068
Create Date: 2026-11-02

The provider adapters now reject these entities before import. This migration
repairs records created before that rule existed while preserving reviewed user
history.
"""

from collections import defaultdict
import json

from alembic import op
import sqlalchemy as sa


revision = "20261102_0069"
down_revision = "20261101_0068"
branch_labels = None
depends_on = None


GOOGLE_BLOCKED_TYPES = frozenset(
    {
        "administrative_area_level_1",
        "administrative_area_level_2",
        "administrative_area_level_3",
        "bus_station",
        "country",
        "intersection",
        "light_rail_station",
        "locality",
        "neighborhood",
        "plus_code",
        "postal_code",
        "premise",
        "route",
        "street_address",
        "subpremise",
        "subway_station",
        "train_station",
        "transit_station",
    }
)
GOOGLE_GENERIC_TYPES = frozenset({"establishment", "point_of_interest"})
OSM_BLOCKED_HIGHWAYS = frozenset(
    {"bus_stop", "crossing", "motorway_junction", "platform", "traffic_signals"}
)
OSM_BLOCKED_PUBLIC_TRANSPORT = frozenset(
    {"platform", "station", "stop_area", "stop_position"}
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("businesses") or not inspector.has_table(
        "source_observations"
    ):
        return

    metadata = sa.MetaData()
    businesses = sa.Table("businesses", metadata, autoload_with=bind)
    observations = sa.Table("source_observations", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(
            observations.c.business_id,
            observations.c.source,
            observations.c.raw_payload,
        ).where(
            sa.func.lower(observations.c.source).in_(
                ("google_places", "google_places_seed", "openstreetmap", "openstreetmap_seed")
            )
        )
    ).all()

    states: dict[str, set[bool]] = defaultdict(set)
    for row in rows:
        state = _entity_state(row.source, _payload(row.raw_payload))
        if state is not None:
            states[row.business_id].add(state)
    invalid_ids = [
        business_id
        for business_id, entity_states in states.items()
        if False in entity_states and True not in entity_states
    ]
    if not invalid_ids:
        return

    for business_ids in _chunks(invalid_ids):
        bind.execute(
            businesses.update()
            .where(
                businesses.c.id.in_(business_ids),
                businesses.c.status == "active",
            )
            .values(status="quarantined")
        )

        if inspector.has_table("business_facts"):
            facts = sa.Table("business_facts", metadata, autoload_with=bind)
            values = {"quality_state": "rejected"}
            if "resolution_state" in facts.c.keys():
                values["resolution_state"] = "unknown"
            bind.execute(
                facts.update()
                .where(facts.c.business_id.in_(business_ids))
                .values(**values)
            )

        if inspector.has_table("source_items"):
            source_items = sa.Table("source_items", metadata, autoload_with=bind)
            bind.execute(
                source_items.update()
                .where(source_items.c.business_id.in_(business_ids))
                .values(state="rejected")
            )

        if inspector.has_table("audience_results"):
            results = sa.Table("audience_results", metadata, autoload_with=bind)
            conditions = [results.c.business_id.in_(business_ids)]
            for column in (
                "reviewed_at",
                "shortlisted_at",
                "contacted_at",
                "outreach_lead_id",
            ):
                if column in results.c.keys():
                    conditions.append(results.c[column].is_(None))
            bind.execute(results.delete().where(*conditions))


def downgrade() -> None:
    # Provider evidence rejected by this migration remains available for audit,
    # but a non-business record must not be restored automatically.
    pass


def _entity_state(source: str, payload: dict) -> bool | None:
    raw = _nested_raw(payload)
    provider = str(source or "").strip().lower()
    if provider in {"google_places", "google_places_seed"}:
        types = {
            str(value).strip().lower()
            for value in (raw.get("types") or [])
            if str(value).strip()
        }
        if types & GOOGLE_BLOCKED_TYPES:
            return False
        if types - GOOGLE_GENERIC_TYPES:
            return True
        return None
    if provider in {"openstreetmap", "openstreetmap_seed"}:
        tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
        if (
            str(tags.get("highway") or "").lower() in OSM_BLOCKED_HIGHWAYS
            or str(tags.get("public_transport") or "").lower()
            in OSM_BLOCKED_PUBLIC_TRANSPORT
            or str(tags.get("railway") or "").lower()
            in {"halt", "platform", "station", "stop"}
        ):
            return False
        if any(tags.get(key) for key in ("craft", "office", "shop")):
            return True
    return None


def _nested_raw(payload: dict) -> dict:
    merged: dict = {}
    layers: list[dict] = []
    current = payload
    while isinstance(current, dict):
        layers.append(current)
        nested = current.get("raw")
        if not isinstance(nested, dict):
            break
        current = nested
    for layer in reversed(layers):
        merged.update(layer)
    return merged


def _payload(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _chunks(values: list[str], size: int = 500):
    for index in range(0, len(values), size):
        yield values[index : index + size]
