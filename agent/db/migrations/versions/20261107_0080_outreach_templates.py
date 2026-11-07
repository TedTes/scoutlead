"""add reusable outreach message structures

Revision ID: 20261107_0080
Revises: 20261104_0079
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20261107_0080"
down_revision = "20261104_0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outreach_templates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("structure", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_outreach_templates_workspace_name",
        ),
    )
    op.create_index(
        op.f("ix_outreach_templates_workspace_id"),
        "outreach_templates",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_outreach_templates_workspace_id"),
        table_name="outreach_templates",
    )
    op.drop_table("outreach_templates")
