"""add evidence-grounded outreach packages

Revision ID: 20261014_0051
Revises: 20261014_0050
Create Date: 2026-10-14
"""

from alembic import op
import sqlalchemy as sa


revision = "20261014_0051"
down_revision = "20261014_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("outreach_packages"):
        return
    op.create_table(
        "outreach_packages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=True),
        sa.Column("audience_result_id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["audience_result_id"], ["audience_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "audience_result_id",
            name="uq_outreach_packages_workspace_result",
        ),
    )
    op.create_index("ix_outreach_packages_workspace_id", "outreach_packages", ["workspace_id"])
    op.create_index("ix_outreach_packages_audience_result_id", "outreach_packages", ["audience_result_id"])
    op.create_index("ix_outreach_packages_business_id", "outreach_packages", ["business_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("outreach_packages"):
        op.drop_table("outreach_packages")
