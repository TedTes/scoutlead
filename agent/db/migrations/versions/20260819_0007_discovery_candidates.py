"""add discovery candidates

Revision ID: 20260819_0007
Revises: 20260819_0006
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0007"
down_revision = "20260819_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("discovery_candidates"):
        return
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("geography", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("candidate_type", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_discovery_candidates_campaign_id"),
        "discovery_candidates",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_candidate_type"),
        "discovery_candidates",
        ["candidate_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_lead_id"),
        "discovery_candidates",
        ["lead_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_candidates_product_id"),
        "discovery_candidates",
        ["product_id"],
        unique=False,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("discovery_candidates"):
        return
    op.drop_index(op.f("ix_discovery_candidates_product_id"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_lead_id"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_candidate_type"), table_name="discovery_candidates")
    op.drop_index(op.f("ix_discovery_candidates_campaign_id"), table_name="discovery_candidates")
    op.drop_table("discovery_candidates")
