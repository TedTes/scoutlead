"""add generated demo sites

Revision ID: 20261013_0047
Revises: 20261013_0046
"""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0047"
down_revision = "20261013_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_sites",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(255), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("audience_result_id", sa.String(64), sa.ForeignKey("audience_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("business_id", sa.String(64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("share_token", sa.String(96), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("outreach_message", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "audience_result_id", name="uq_demo_sites_workspace_result"),
    )
    for column in ("workspace_id", "audience_result_id", "business_id", "share_token", "status"):
        op.create_index(f"ix_demo_sites_{column}", "demo_sites", [column])


def downgrade() -> None:
    op.drop_table("demo_sites")
