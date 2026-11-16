#!/usr/bin/env python3
"""Move canonical business catalog rows between ScoutLead environments.

This utility is intentionally narrow: it exports/imports only the canonical
business catalog (businesses, current attributes, contacts, niche memberships,
and the referenced definitions). It does not copy workspaces, saved searches,
lead workflow state, queue jobs, or provider work items.

Destructive cleanup is explicit. ``reset-catalog`` truncates ``businesses``
with PostgreSQL CASCADE so a backed-up non-production environment can be
rebuilt from a small representative bundle without leaving dangling rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import MetaData, Table, bindparam, create_engine, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert


CATALOG_TABLES = (
    "signal_definitions",
    "niches",
    "businesses",
    "business_attributes",
    "contacts",
    "business_niche_memberships",
)


def _engine():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    return create_engine(database_url)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _load_ids(path: str) -> list[str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    values = payload.get("business_ids", payload) if isinstance(payload, dict) else payload
    return sorted({str(value) for value in values})


def _reflect(engine: Any) -> dict[str, Table]:
    metadata = MetaData()
    available = set(inspect(engine).get_table_names())
    missing = [table for table in CATALOG_TABLES if table not in available]
    if missing:
        raise SystemExit(f"Missing required tables: {', '.join(missing)}")
    return {
        name: Table(name, metadata, autoload_with=engine)
        for name in CATALOG_TABLES
    }


def _rows(connection: Any, statement: Any) -> list[dict[str, Any]]:
    return [
        {str(key): _json_value(value) for key, value in dict(row).items()}
        for row in connection.execute(statement).mappings()
    ]


def export_bundle(ids_path: str, output_path: str) -> dict[str, Any]:
    engine = _engine()
    tables = _reflect(engine)
    business_ids = _load_ids(ids_path)
    with engine.connect() as connection:
        businesses = _rows(
            connection,
            select(tables["businesses"]).where(
                tables["businesses"].c.id.in_(business_ids)
            ),
        )
        exported_ids = [str(row["id"]) for row in businesses]
        attributes = _rows(
            connection,
            select(tables["business_attributes"]).where(
                tables["business_attributes"].c.business_id.in_(exported_ids)
            ),
        )
        contacts = _rows(
            connection,
            select(tables["contacts"]).where(
                tables["contacts"].c.business_id.in_(exported_ids)
            ),
        )
        memberships = _rows(
            connection,
            select(tables["business_niche_memberships"]).where(
                tables["business_niche_memberships"].c.business_id.in_(exported_ids)
            ),
        )
        niche_ids = sorted({str(row["niche_id"]) for row in memberships})
        definition_ids = sorted(
            {
                str(row["signal_definition_id"])
                for row in attributes
                if row.get("signal_definition_id")
            }
        )
        niches = _rows(
            connection,
            select(tables["niches"]).where(tables["niches"].c.id.in_(niche_ids)),
        )
        definitions = _rows(
            connection,
            select(tables["signal_definitions"]).where(
                tables["signal_definitions"].c.id.in_(definition_ids)
            ),
        )

    bundle = {
        "schema_version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "requested_business_count": len(business_ids),
        "tables": {
            "signal_definitions": definitions,
            "niches": niches,
            "businesses": businesses,
            "business_attributes": attributes,
            "contacts": contacts,
            "business_niche_memberships": memberships,
        },
    }
    Path(output_path).write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), default=str),
        encoding="utf-8",
    )
    return {
        "output_path": output_path,
        "requested_businesses": len(business_ids),
        **{name: len(rows) for name, rows in bundle["tables"].items()},
    }


def _coerce_row(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in table.columns:
        if column.name not in row:
            continue
        value = row[column.name]
        try:
            python_type = column.type.python_type
        except (AttributeError, NotImplementedError):
            python_type = None
        if value is not None and isinstance(python_type, type):
            if python_type is datetime and isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            elif python_type is date and isinstance(value, str):
                value = date.fromisoformat(value)
        result[column.name] = value
    return result


def _upsert_reference(
    connection: Any,
    table: Table,
    rows: Iterable[dict[str, Any]],
    *,
    natural_key: str,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in rows:
        row = _coerce_row(table, raw)
        source_id = str(row["id"])
        natural_value = row[natural_key]
        existing_id = connection.execute(
            select(table.c.id).where(table.c[natural_key] == natural_value)
        ).scalar_one_or_none()
        if existing_id is None:
            connection.execute(pg_insert(table).values(**row).on_conflict_do_nothing())
            existing_id = connection.execute(
                select(table.c.id).where(table.c[natural_key] == natural_value)
            ).scalar_one()
        mapping[source_id] = str(existing_id)
    return mapping


def _business_target_id(connection: Any, table: Table, row: dict[str, Any]) -> str | None:
    existing = connection.execute(
        select(table.c.id).where(table.c.id == row["id"])
    ).scalar_one_or_none()
    if existing:
        return str(existing)
    normalized_name = row.get("normalized_name")
    domain = row.get("domain")
    if normalized_name and domain:
        existing = connection.execute(
            select(table.c.id).where(
                table.c.normalized_name == normalized_name,
                table.c.domain == domain,
            )
        ).scalar_one_or_none()
        if existing:
            return str(existing)
    return None


def _batches(rows: list[dict[str, Any]], size: int = 1000) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _bulk_insert(connection: Any, table: Table, rows: list[dict[str, Any]]) -> None:
    for batch in _batches(rows):
        connection.execute(table.insert(), batch)


def _bulk_update_by_id(connection: Any, table: Table, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    value_columns = [
        key for key in rows[0] if key not in {"id", "business_id", "attribute_key", "created_at"}
    ]
    statement = (
        table.update()
        .where(table.c.id == bindparam("target_id"))
        .values(**{key: bindparam(f"value_{key}") for key in value_columns})
    )
    parameters = [
        {
            "target_id": row["id"],
            **{f"value_{key}": row.get(key) for key in value_columns},
        }
        for row in rows
    ]
    for batch in _batches(parameters):
        connection.execute(statement, batch)


def import_bundle(bundle_path: str) -> dict[str, Any]:
    bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    source = bundle["tables"]
    engine = _engine()
    tables = _reflect(engine)
    counts = {
        "businesses_inserted": 0,
        "businesses_mapped_existing": 0,
        "attributes_inserted_or_updated": 0,
        "contacts_inserted": 0,
        "memberships_inserted_or_updated": 0,
    }
    with engine.begin() as connection:
        definition_map = _upsert_reference(
            connection,
            tables["signal_definitions"],
            source.get("signal_definitions", []),
            natural_key="key",
        )
        niche_map = _upsert_reference(
            connection,
            tables["niches"],
            source.get("niches", []),
            natural_key="slug",
        )

        business_table = tables["businesses"]
        existing_businesses = connection.execute(
            select(
                business_table.c.id,
                business_table.c.normalized_name,
                business_table.c.domain,
            )
        ).mappings().all()
        existing_business_ids = {str(row["id"]) for row in existing_businesses}
        identity_to_id = {
            (row["normalized_name"], row["domain"]): str(row["id"])
            for row in existing_businesses
            if row["normalized_name"] and row["domain"]
        }
        business_map: dict[str, str] = {}
        business_inserts: list[dict[str, Any]] = []
        for raw in source.get("businesses", []):
            row = _coerce_row(business_table, raw)
            source_id = str(row["id"])
            identity = (row.get("normalized_name"), row.get("domain"))
            target_id = source_id if source_id in existing_business_ids else None
            if target_id is None and all(identity):
                target_id = identity_to_id.get(identity)
            if target_id is None:
                target_id = source_id
                business_inserts.append(row)
                existing_business_ids.add(source_id)
                if all(identity):
                    identity_to_id[identity] = source_id
                counts["businesses_inserted"] += 1
            else:
                counts["businesses_mapped_existing"] += 1
            business_map[source_id] = target_id
        _bulk_insert(connection, business_table, business_inserts)

        attribute_table = tables["business_attributes"]
        target_business_ids = sorted(set(business_map.values()))
        existing_attributes = connection.execute(
            select(
                attribute_table.c.id,
                attribute_table.c.business_id,
                attribute_table.c.attribute_key,
                attribute_table.c.observed_at,
            ).where(attribute_table.c.business_id.in_(target_business_ids))
        ).mappings().all()
        attribute_by_key = {
            (str(row["business_id"]), str(row["attribute_key"])): row
            for row in existing_attributes
        }
        attribute_ids = {
            str(value)
            for value in connection.execute(select(attribute_table.c.id)).scalars()
        }
        attribute_inserts: list[dict[str, Any]] = []
        attribute_updates: list[dict[str, Any]] = []
        for raw in source.get("business_attributes", []):
            row = _coerce_row(attribute_table, raw)
            source_business_id = str(row["business_id"])
            if source_business_id not in business_map:
                continue
            row["business_id"] = business_map[source_business_id]
            if row.get("signal_definition_id"):
                row["signal_definition_id"] = definition_map.get(
                    str(row["signal_definition_id"])
                )
            # Attribute IDs are globally generated, but a mapped existing
            # business may already own this key under another ID.
            key = (str(row["business_id"]), str(row["attribute_key"]))
            existing = attribute_by_key.get(key)
            if existing:
                incoming_observed = row.get("observed_at")
                if not incoming_observed or (
                    existing["observed_at"]
                    and incoming_observed < existing["observed_at"]
                ):
                    continue
                row["id"] = str(existing["id"])
                attribute_updates.append(row)
            else:
                if str(row["id"]) in attribute_ids:
                    row["id"] = f"{row['id']}_{row['business_id'][-8:]}"
                attribute_ids.add(str(row["id"]))
                attribute_inserts.append(row)
                attribute_by_key[key] = {
                    "id": row["id"],
                    "business_id": row["business_id"],
                    "attribute_key": row["attribute_key"],
                    "observed_at": row.get("observed_at"),
                }
            counts["attributes_inserted_or_updated"] += 1
        _bulk_insert(connection, attribute_table, attribute_inserts)
        _bulk_update_by_id(connection, attribute_table, attribute_updates)

        contact_table = tables["contacts"]
        existing_contacts = connection.execute(
            select(
                contact_table.c.id,
                contact_table.c.business_id,
                contact_table.c.email,
                contact_table.c.phone,
            ).where(contact_table.c.business_id.in_(target_business_ids))
        ).mappings().all()
        contact_keys = {
            (
                str(row["business_id"]),
                "email" if row["email"] else "phone",
                str(row["email"] or row["phone"] or ""),
            )
            for row in existing_contacts
        }
        contact_ids = {
            str(value) for value in connection.execute(select(contact_table.c.id)).scalars()
        }
        contact_inserts: list[dict[str, Any]] = []
        for raw in source.get("contacts", []):
            row = _coerce_row(contact_table, raw)
            source_business_id = str(row["business_id"])
            if source_business_id not in business_map:
                continue
            row["business_id"] = business_map[source_business_id]
            kind = "email" if row.get("email") else "phone"
            value = str(row.get("email") or row.get("phone") or "")
            contact_key = (str(row["business_id"]), kind, value)
            if value and contact_key in contact_keys:
                continue
            if str(row["id"]) in contact_ids:
                row["id"] = f"{row['id']}_{row['business_id'][-8:]}"
            contact_ids.add(str(row["id"]))
            contact_keys.add(contact_key)
            contact_inserts.append(row)
            counts["contacts_inserted"] += 1
        _bulk_insert(connection, contact_table, contact_inserts)

        membership_table = tables["business_niche_memberships"]
        existing_memberships = connection.execute(
            select(
                membership_table.c.id,
                membership_table.c.business_id,
                membership_table.c.niche_id,
                membership_table.c.market_key,
            ).where(membership_table.c.business_id.in_(target_business_ids))
        ).mappings().all()
        membership_by_key = {
            (
                str(row["business_id"]),
                str(row["niche_id"]),
                str(row["market_key"]),
            ): str(row["id"])
            for row in existing_memberships
        }
        membership_ids = {
            str(value)
            for value in connection.execute(select(membership_table.c.id)).scalars()
        }
        membership_inserts: list[dict[str, Any]] = []
        membership_updates: list[dict[str, Any]] = []
        for raw in source.get("business_niche_memberships", []):
            row = _coerce_row(membership_table, raw)
            source_business_id = str(row["business_id"])
            source_niche_id = str(row["niche_id"])
            if source_business_id not in business_map or source_niche_id not in niche_map:
                continue
            row["business_id"] = business_map[source_business_id]
            row["niche_id"] = niche_map[source_niche_id]
            key = (
                str(row["business_id"]),
                str(row["niche_id"]),
                str(row["market_key"]),
            )
            existing = membership_by_key.get(key)
            if existing:
                row["id"] = existing
                membership_updates.append(row)
            else:
                if str(row["id"]) in membership_ids:
                    row["id"] = f"{row['id']}_{row['business_id'][-8:]}"
                membership_ids.add(str(row["id"]))
                membership_by_key[key] = str(row["id"])
                membership_inserts.append(row)
            counts["memberships_inserted_or_updated"] += 1
        _bulk_insert(connection, membership_table, membership_inserts)
        _bulk_update_by_id(connection, membership_table, membership_updates)

    return counts


def reset_catalog() -> dict[str, Any]:
    engine = _engine()
    with engine.begin() as connection:
        before = int(connection.execute(text("SELECT count(*) FROM businesses")).scalar_one())
        connection.execute(text("TRUNCATE TABLE businesses CASCADE"))
        after = int(connection.execute(text("SELECT count(*) FROM businesses")).scalar_one())
    return {"businesses_before": before, "businesses_after": after}


def verify() -> dict[str, Any]:
    engine = _engine()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    result: dict[str, Any] = {}
    with engine.connect() as connection:
        for table in CATALOG_TABLES:
            if table in tables:
                result[table] = int(
                    connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                )
        result["active_businesses"] = int(
            connection.execute(
                text("SELECT count(*) FROM businesses WHERE status = 'active'")
            ).scalar_one()
        )
        result["businesses_without_attributes"] = int(
            connection.execute(
                text(
                    """
                    SELECT count(*) FROM businesses b
                    WHERE NOT EXISTS (
                        SELECT 1 FROM business_attributes a WHERE a.business_id = b.id
                    )
                    """
                )
            ).scalar_one()
        )
        result["orphan_attributes"] = int(
            connection.execute(
                text(
                    """
                    SELECT count(*) FROM business_attributes a
                    WHERE NOT EXISTS (SELECT 1 FROM businesses b WHERE b.id = a.business_id)
                    """
                )
            ).scalar_one()
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--ids", required=True)
    export_parser.add_argument("--output", required=True)
    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--bundle", required=True)
    subparsers.add_parser("reset-catalog")
    subparsers.add_parser("verify")
    args = parser.parse_args()

    if args.command == "export":
        result = export_bundle(args.ids, args.output)
    elif args.command == "import":
        result = import_bundle(args.bundle)
    elif args.command == "reset-catalog":
        result = reset_catalog()
    else:
        result = verify()
    json.dump(result, sys.stdout, separators=(",", ":"), default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
