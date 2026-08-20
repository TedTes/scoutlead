"""add campaign sources

Revision ID: 20260820_0008
Revises: 20260819_0007
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260820_0008"
down_revision = "20260819_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "source_preset_id" not in campaign_columns:
        op.add_column("campaigns", sa.Column("source_preset_id", sa.String(length=255), nullable=True))
    if inspector.has_table("campaign_sources"):
        return
    op.create_table(
        "campaign_sources",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=64), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("budget_limit", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_campaign_sources_campaign_id"), "campaign_sources", ["campaign_id"])
    op.create_index(op.f("ix_campaign_sources_provider_id"), "campaign_sources", ["provider_id"])
    op.create_index(op.f("ix_campaign_sources_slot"), "campaign_sources", ["slot"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("campaign_sources"):
        op.drop_index(op.f("ix_campaign_sources_slot"), table_name="campaign_sources")
        op.drop_index(op.f("ix_campaign_sources_provider_id"), table_name="campaign_sources")
        op.drop_index(op.f("ix_campaign_sources_campaign_id"), table_name="campaign_sources")
        op.drop_table("campaign_sources")
    campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "source_preset_id" in campaign_columns:
        op.drop_column("campaigns", "source_preset_id")
