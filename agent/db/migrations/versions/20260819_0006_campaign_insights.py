"""add campaign insights

Revision ID: 20260819_0006
Revises: 20260819_0005
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0006"
down_revision = "20260819_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("campaign_insights"):
        return
    op.create_table(
        "campaign_insights",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("goal_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("icp_verdict", sa.JSON(), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaign_insights_campaign_id"), "campaign_insights", ["campaign_id"], unique=False)
    op.create_index(op.f("ix_campaign_insights_product_id"), "campaign_insights", ["product_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("campaign_insights"):
        return
    op.drop_index(op.f("ix_campaign_insights_product_id"), table_name="campaign_insights")
    op.drop_index(op.f("ix_campaign_insights_campaign_id"), table_name="campaign_insights")
    op.drop_table("campaign_insights")
