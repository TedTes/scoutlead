"""make unknown operational status neutral for lead eligibility

Revision ID: 20261103_0073
Revises: 20261103_0072
Create Date: 2026-11-03

Operational evidence is useful when a provider explicitly reports that a
business is open or closed. Its absence is not evidence of closure. Align the
stored freshness window with the runtime policy and republish recent,
provenanced boolean observations without changing rejected evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261103_0073"
down_revision = "20261103_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    now = datetime.now(timezone.utc)

    if inspector.has_table("signal_definitions"):
        definitions = sa.table(
            "signal_definitions",
            sa.column("key", sa.String),
            sa.column("freshness_days", sa.Integer),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        bind.execute(
            definitions.update()
            .where(definitions.c.key == "business_operational")
            .values(freshness_days=90, updated_at=now)
        )

    if not inspector.has_table("business_facts"):
        return

    facts = sa.table(
        "business_facts",
        sa.column("id", sa.String),
        sa.column("fact_key", sa.String),
        sa.column("value_type", sa.String),
        sa.column("value_boolean", sa.Boolean),
        sa.column("confidence", sa.Integer),
        sa.column("resolution_state", sa.String),
        sa.column("quality_state", sa.String),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("source_observation_id", sa.String),
    )
    rows = bind.execute(
        sa.select(facts.c.id, facts.c.observed_at).where(
            facts.c.fact_key == "business_operational",
            facts.c.value_type == "boolean",
            facts.c.value_boolean.is_not(None),
            facts.c.confidence >= 85,
            facts.c.source_observation_id.is_not(None),
            facts.c.quality_state.in_(("staged", "published")),
            facts.c.observed_at >= now - timedelta(days=90),
        )
    ).all()
    if rows:
        bind.execute(
            facts.update()
            .where(facts.c.id == sa.bindparam("fact_id"))
            .values(
                expires_at=sa.bindparam("expires_at"),
                resolution_state="confirmed",
                quality_state="published",
            ),
            [
                {
                    "fact_id": row.id,
                    "expires_at": row.observed_at + timedelta(days=90),
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    # Do not shorten or unpublish evidence that may already have been used.
    pass
