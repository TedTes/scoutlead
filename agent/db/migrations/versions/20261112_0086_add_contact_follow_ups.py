"""add persistent contact attempt follow-ups

Revision ID: 20261112_0086
Revises: 20261112_0085
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op


revision = "20261112_0086"
down_revision = "20261112_0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("lead_outcomes")
    }
    if "follow_up_at" not in columns:
        op.add_column(
            "lead_outcomes",
            sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_lead_outcomes_follow_up_at",
            "lead_outcomes",
            ["follow_up_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("lead_outcomes")
    }
    if "follow_up_at" not in columns:
        return
    op.drop_index("ix_lead_outcomes_follow_up_at", table_name="lead_outcomes")
    op.drop_column("lead_outcomes", "follow_up_at")
