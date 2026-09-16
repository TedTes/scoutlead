"""add normalized seed niche memberships

Revision ID: 20260915_0017
Revises: 20260908_0016
Create Date: 2026-09-15
"""

from __future__ import annotations

from datetime import datetime
import json
import re
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision = "20260915_0017"
down_revision = "20260908_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("niches"):
        op.create_table(
            "niches",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("slug", sa.String(length=255), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("category", sa.String(length=255), nullable=True),
            sa.Column("default_query", sa.Text(), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_niches_slug"),
        )
        op.create_index(op.f("ix_niches_category"), "niches", ["category"], unique=False)
        op.create_index(op.f("ix_niches_slug"), "niches", ["slug"], unique=False)

    inspector = sa.inspect(bind)
    if not inspector.has_table("seed_batches"):
        op.create_table(
            "seed_batches",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("niche_id", sa.String(length=64), nullable=True),
            sa.Column("market_key", sa.String(length=255), nullable=True),
            sa.Column("source", sa.String(length=255), nullable=False),
            sa.Column("query", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("found_count", sa.Integer(), nullable=False),
            sa.Column("inserted_count", sa.Integer(), nullable=False),
            sa.Column("updated_count", sa.Integer(), nullable=False),
            sa.Column("source_observation_count", sa.Integer(), nullable=False),
            sa.Column("cost_cents", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_seed_batches_market_key"), "seed_batches", ["market_key"])
        op.create_index(op.f("ix_seed_batches_niche_id"), "seed_batches", ["niche_id"])
        op.create_index(op.f("ix_seed_batches_source"), "seed_batches", ["source"])
        op.create_index(op.f("ix_seed_batches_status"), "seed_batches", ["status"])

    inspector = sa.inspect(bind)
    if not inspector.has_table("business_niche_memberships"):
        op.create_table(
            "business_niche_memberships",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("business_id", sa.String(length=64), nullable=False),
            sa.Column("niche_id", sa.String(length=64), nullable=False),
            sa.Column("market_key", sa.String(length=255), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("source_observation_id", sa.String(length=64), nullable=True),
            sa.Column("seed_batch_id", sa.String(length=255), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
            sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
            sa.ForeignKeyConstraint(["seed_batch_id"], ["seed_batches.id"]),
            sa.ForeignKeyConstraint(["source_observation_id"], ["source_observations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "business_id",
                "niche_id",
                "market_key",
                name="uq_business_niche_memberships_business_niche_market",
            ),
        )
        op.create_index(
            op.f("ix_business_niche_memberships_business_id"),
            "business_niche_memberships",
            ["business_id"],
        )
        op.create_index(
            op.f("ix_business_niche_memberships_market_key"),
            "business_niche_memberships",
            ["market_key"],
        )
        op.create_index(
            op.f("ix_business_niche_memberships_niche_id"),
            "business_niche_memberships",
            ["niche_id"],
        )
        op.create_index(
            op.f("ix_business_niche_memberships_seed_batch_id"),
            "business_niche_memberships",
            ["seed_batch_id"],
        )
        op.create_index(
            op.f("ix_business_niche_memberships_source_observation_id"),
            "business_niche_memberships",
            ["source_observation_id"],
        )

    _backfill_seed_metadata(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("business_niche_memberships"):
        op.drop_index(
            op.f("ix_business_niche_memberships_source_observation_id"),
            table_name="business_niche_memberships",
        )
        op.drop_index(
            op.f("ix_business_niche_memberships_seed_batch_id"),
            table_name="business_niche_memberships",
        )
        op.drop_index(
            op.f("ix_business_niche_memberships_niche_id"),
            table_name="business_niche_memberships",
        )
        op.drop_index(
            op.f("ix_business_niche_memberships_market_key"),
            table_name="business_niche_memberships",
        )
        op.drop_index(
            op.f("ix_business_niche_memberships_business_id"),
            table_name="business_niche_memberships",
        )
        op.drop_table("business_niche_memberships")

    if inspector.has_table("seed_batches"):
        op.drop_index(op.f("ix_seed_batches_status"), table_name="seed_batches")
        op.drop_index(op.f("ix_seed_batches_source"), table_name="seed_batches")
        op.drop_index(op.f("ix_seed_batches_niche_id"), table_name="seed_batches")
        op.drop_index(op.f("ix_seed_batches_market_key"), table_name="seed_batches")
        op.drop_table("seed_batches")

    if inspector.has_table("niches"):
        op.drop_index(op.f("ix_niches_slug"), table_name="niches")
        op.drop_index(op.f("ix_niches_category"), table_name="niches")
        op.drop_table("niches")


def _backfill_seed_metadata(bind) -> None:
    inspector = sa.inspect(bind)
    required_tables = {
        "source_observations",
        "niches",
        "seed_batches",
        "business_niche_memberships",
    }
    if any(not inspector.has_table(table_name) for table_name in required_tables):
        return

    niches = sa.table(
        "niches",
        sa.column("id", sa.String(length=64)),
        sa.column("slug", sa.String(length=255)),
        sa.column("label", sa.String(length=255)),
        sa.column("category", sa.String(length=255)),
        sa.column("default_query", sa.Text()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    seed_batches = sa.table(
        "seed_batches",
        sa.column("id", sa.String(length=255)),
        sa.column("niche_id", sa.String(length=64)),
        sa.column("market_key", sa.String(length=255)),
        sa.column("source", sa.String(length=255)),
        sa.column("query", sa.Text()),
        sa.column("status", sa.String(length=64)),
        sa.column("started_at", sa.DateTime(timezone=True)),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("found_count", sa.Integer()),
        sa.column("inserted_count", sa.Integer()),
        sa.column("updated_count", sa.Integer()),
        sa.column("source_observation_count", sa.Integer()),
        sa.column("cost_cents", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    memberships = sa.table(
        "business_niche_memberships",
        sa.column("id", sa.String(length=64)),
        sa.column("business_id", sa.String(length=64)),
        sa.column("niche_id", sa.String(length=64)),
        sa.column("market_key", sa.String(length=255)),
        sa.column("confidence", sa.Float()),
        sa.column("evidence", sa.JSON()),
        sa.column("source_observation_id", sa.String(length=64)),
        sa.column("seed_batch_id", sa.String(length=255)),
        sa.column("first_seen_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    observations = sa.table(
        "source_observations",
        sa.column("id", sa.String(length=64)),
        sa.column("business_id", sa.String(length=64)),
        sa.column("source", sa.String(length=255)),
        sa.column("raw_payload", sa.JSON()),
        sa.column("observed_at", sa.DateTime(timezone=True)),
    )

    niche_ids = {row.slug: row.id for row in bind.execute(sa.select(niches.c.id, niches.c.slug))}
    seed_batch_ids = {row.id for row in bind.execute(sa.select(seed_batches.c.id))}
    membership_keys = {
        (row.business_id, row.niche_id, row.market_key)
        for row in bind.execute(
            sa.select(memberships.c.business_id, memberships.c.niche_id, memberships.c.market_key)
        )
    }
    batch_counts: dict[str, int] = {}

    for row in bind.execute(sa.select(observations)):
        raw = _raw_payload(row.raw_payload)
        seed_niche = _clean_text(raw.get("seed_niche"))
        if not seed_niche:
            continue

        now = row.observed_at or datetime.utcnow()
        slug = _niche_slug(seed_niche)
        niche_id = niche_ids.get(slug)
        if niche_id is None:
            niche_id = _new_id("niche")
            bind.execute(
                niches.insert().values(
                    id=niche_id,
                    slug=slug,
                    label=_niche_label(seed_niche),
                    category=seed_niche,
                    default_query=_clean_text(raw.get("query") or raw.get("search_query")),
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            niche_ids[slug] = niche_id

        market_key = _semantic_key(
            raw.get("seed_market")
            or raw.get("geography")
            or raw.get("formattedAddress")
            or raw.get("address")
        )
        batch_id = _clean_text(raw.get("seed_batch_id")) or None
        if batch_id and batch_id not in seed_batch_ids:
            bind.execute(
                seed_batches.insert().values(
                    id=batch_id,
                    niche_id=niche_id,
                    market_key=market_key,
                    source=row.source or _clean_text(raw.get("seed_source")) or "manual_seed",
                    query=_clean_text(raw.get("query") or raw.get("search_query")),
                    status="completed",
                    started_at=now,
                    completed_at=now,
                    found_count=0,
                    inserted_count=0,
                    updated_count=0,
                    source_observation_count=0,
                    cost_cents=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            seed_batch_ids.add(batch_id)

        membership_key = (row.business_id, niche_id, market_key)
        if membership_key not in membership_keys:
            bind.execute(
                memberships.insert().values(
                    id=_new_id("bizniche"),
                    business_id=row.business_id,
                    niche_id=niche_id,
                    market_key=market_key,
                    confidence=1.0,
                    evidence=[
                        {
                            "type": "seed_import",
                            "source": row.source,
                            "batch_id": batch_id,
                            "query": _clean_text(raw.get("query") or raw.get("search_query")),
                            "signals": (
                                raw.get("signals")
                                if isinstance(raw.get("signals"), list)
                                else []
                            ),
                            "source_observation_id": row.id,
                        }
                    ],
                    source_observation_id=row.id,
                    seed_batch_id=batch_id,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            membership_keys.add(membership_key)
            if batch_id:
                batch_counts[batch_id] = batch_counts.get(batch_id, 0) + 1

    for batch_id, count in batch_counts.items():
        bind.execute(
            seed_batches.update()
            .where(seed_batches.c.id == batch_id)
            .values(
                found_count=count,
                source_observation_count=count,
                updated_at=datetime.utcnow(),
            )
        )


def _raw_payload(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_text(value) -> str:
    return " ".join(str(value or "").split())


def _niche_slug(value: str | None) -> str:
    normalized = _clean_text(value or "uncategorized").lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = normalized.strip("_")
    return normalized or "uncategorized"


def _niche_label(value: str | None) -> str:
    slug = _niche_slug(value)
    return " ".join(part.capitalize() for part in slug.split("_") if part) or "Uncategorized"


def _semantic_key(value) -> str:
    normalized = _clean_text(value).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = " ".join(normalized.split())
    return normalized or "unknown"
