"""remove duplicated raw payloads from resolved attributes

Revision ID: 20261113_0096
Revises: 20261113_0095
Create Date: 2026-11-13

Migration 0094 copied the complete provider response onto every attribute
derived from that response.  The typed value and provenance columns already
contain everything matching and filtering need. Keep only one internal source
payload row per business/provider and remove the payload from resolved
attributes.

No new evidence table is introduced.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re

from alembic import op
import sqlalchemy as sa


revision = "20261113_0096"
down_revision = "20261113_0095"
branch_labels = None
depends_on = None

SOURCE_PAYLOAD_PREFIX = "__source_payload__:"


def _source_key(source_provider: str | None) -> str:
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        (source_provider or "unknown").strip().lower(),
    ).strip("_")
    return f"{SOURCE_PAYLOAD_PREFIX}{normalized or 'unknown'}"


def _replacement_id(business_id: str, attribute_key: str) -> str:
    digest = hashlib.sha256(
        f"{business_id}\0{attribute_key}\0resolved".encode("utf-8")
    ).hexdigest()[:32]
    return f"business_attribute_{digest}"


def _payload(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "business_attributes" not in tables:
        return

    metadata = sa.MetaData()
    attributes = sa.Table("business_attributes", metadata, autoload_with=bind)
    column_names = set(attributes.c.keys())
    if "evidence" in column_names and "attribute_key" in column_names:
        rows = list(bind.execute(sa.select(attributes)).mappings())
        existing_carriers = {
            (str(row["business_id"]), str(row["attribute_key"]))
            for row in rows
            if str(row.get("attribute_key") or "").startswith(
                SOURCE_PAYLOAD_PREFIX
            )
        }
        latest_by_source: dict[tuple[str, str], dict] = {}
        for row in rows:
            if not _payload(row.get("evidence")):
                continue
            attribute_key = str(row.get("attribute_key") or "")
            if attribute_key.startswith(SOURCE_PAYLOAD_PREFIX):
                continue
            business_id = str(row["business_id"])
            carrier_key = _source_key(row.get("source_provider"))
            key = (business_id, carrier_key)
            current = latest_by_source.get(key)
            if current is None or (
                row.get("observed_at") or datetime.min.replace(tzinfo=timezone.utc)
            ) > (
                current.get("observed_at")
                or datetime.min.replace(tzinfo=timezone.utc)
            ):
                latest_by_source[key] = dict(row)

        for (business_id, carrier_key), row in latest_by_source.items():
            if (business_id, carrier_key) in existing_carriers:
                continue
            original_key = str(row["attribute_key"])
            replacement = {
                name: row.get(name)
                for name in column_names
                if name in row
            }
            replacement.update(
                id=_replacement_id(business_id, original_key),
                attribute_key=original_key,
                evidence={},
            )

            carrier_values = {"attribute_key": carrier_key}
            for name, value in {
                "signal_definition_id": None,
                "value_type": "text",
                "value_text": row.get("value_text") or original_key,
                "value_number": None,
                "value_boolean": None,
                "value_json": None,
                "opportunity_score": None,
                "score_version": None,
                "score_reason": None,
                "expires_at": None,
            }.items():
                if name in column_names:
                    carrier_values[name] = value

            # Reuse the original row for the source payload so membership and
            # lineage identifiers remain valid. Reinsert its resolved value as
            # a compact attribute row.
            bind.execute(
                attributes.update()
                .where(attributes.c.id == row["id"])
                .values(**carrier_values)
            )
            bind.execute(attributes.insert().values(**replacement))
            existing_carriers.add((business_id, carrier_key))

        bind.execute(
            attributes.update()
            .where(~attributes.c.attribute_key.startswith(SOURCE_PAYLOAD_PREFIX))
            .values(evidence={})
        )

    # Defensive cleanup in case an unreleased version of this revision was
    # applied to a disposable environment while it was being developed.
    attribute_columns = {
        column["name"] for column in inspector.get_columns("business_attributes")
    }
    if "source_evidence_id" in attribute_columns:
        indexes = {
            item["name"] for item in inspector.get_indexes("business_attributes")
        }
        if "ix_business_attributes_source_evidence_id" in indexes:
            op.drop_index(
                "ix_business_attributes_source_evidence_id",
                table_name="business_attributes",
            )
        with op.batch_alter_table("business_attributes") as batch:
            for foreign_key in inspector.get_foreign_keys("business_attributes"):
                if (
                    foreign_key.get("referred_table") == "business_evidence"
                    and foreign_key.get("name")
                ):
                    batch.drop_constraint(foreign_key["name"], type_="foreignkey")
            batch.drop_column("source_evidence_id")

    if "business_evidence" in tables:
        op.drop_table("business_evidence")


def downgrade() -> None:
    raise RuntimeError(
        "20261113_0096 is intentionally irreversible: duplicated provider "
        "payloads were removed from derived attributes."
    )
