"""tighten freshness window for the mobile viewport signal

Revision ID: 20261103_0074
Revises: 20261103_0073
Create Date: 2026-11-03

Mobile-viewport presence can change whenever a business re-platforms, yet
these facts were held as "confirmed" evidence for a full 30 days. Shorten
the window to 14 days and recompute expires_at for already-stored facts so
stale rows pick up the shorter window immediately.
"""

from __future__ import annotations

from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision = "20261103_0074"
down_revision = "20261103_0073"
branch_labels = None
depends_on = None

TIGHTENED_SIGNAL_KEYS = ("mobile_viewport_present",)
NEW_FRESHNESS_DAYS = 14


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("signal_definitions"):
        definitions = sa.table(
            "signal_definitions",
            sa.column("key", sa.String),
            sa.column("freshness_days", sa.Integer),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        bind.execute(
            definitions.update()
            .where(definitions.c.key.in_(TIGHTENED_SIGNAL_KEYS))
            .values(freshness_days=NEW_FRESHNESS_DAYS, updated_at=sa.func.now())
        )

    if not inspector.has_table("business_facts"):
        return

    facts = sa.table(
        "business_facts",
        sa.column("id", sa.String),
        sa.column("fact_key", sa.String),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
    )
    rows = bind.execute(
        sa.select(facts.c.id, facts.c.observed_at).where(
            facts.c.fact_key.in_(TIGHTENED_SIGNAL_KEYS),
            facts.c.observed_at.is_not(None),
        )
    ).all()
    if rows:
        bind.execute(
            facts.update()
            .where(facts.c.id == sa.bindparam("fact_id"))
            .values(expires_at=sa.bindparam("expires_at")),
            [
                {
                    "fact_id": row.id,
                    "expires_at": row.observed_at + timedelta(days=NEW_FRESHNESS_DAYS),
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("signal_definitions"):
        definitions = sa.table(
            "signal_definitions",
            sa.column("key", sa.String),
            sa.column("freshness_days", sa.Integer),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        bind.execute(
            definitions.update()
            .where(definitions.c.key.in_(TIGHTENED_SIGNAL_KEYS))
            .values(freshness_days=30, updated_at=sa.func.now())
        )
    # Previously shortened fact expirations are not restored; lengthening
    # them back out would resurrect evidence as "fresh" without re-checking it.
