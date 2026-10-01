"""add business index segments

Revision ID: 20261001_0026
Revises: 20260930_0025
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20261001_0026"
down_revision = "20260930_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("business_index_segments"):
        return
    op.create_table(
        "business_index_segments",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("niche_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("market_key", sa.String(length=255), nullable=False),
        sa.Column("market_label", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("demand_count", sa.Integer(), nullable=False),
        sa.Column("target_business_count", sa.Integer(), nullable=False),
        sa.Column("source_plan", sa.JSON(), nullable=False),
        sa.Column("source_state", sa.JSON(), nullable=False),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "niche_id",
            "market_key",
            name="uq_business_index_segments_niche_market",
        ),
    )
    op.create_index(
        op.f("ix_business_index_segments_niche_id"),
        "business_index_segments",
        ["niche_id"],
    )
    op.create_index(
        op.f("ix_business_index_segments_product_id"),
        "business_index_segments",
        ["product_id"],
    )
    op.create_index(
        op.f("ix_business_index_segments_market_key"),
        "business_index_segments",
        ["market_key"],
    )
    op.create_index(
        op.f("ix_business_index_segments_status"),
        "business_index_segments",
        ["status"],
    )
    op.create_index(
        op.f("ix_business_index_segments_next_refresh_at"),
        "business_index_segments",
        ["next_refresh_at"],
    )
    op.create_index(
        "ix_businesses_status_market_category",
        "businesses",
        ["status", "market_key", "category_key"],
    )
    op.create_index(
        "ix_business_niche_memberships_niche_market",
        "business_niche_memberships",
        ["niche_id", "market_key"],
    )
    op.create_index(
        "ix_contacts_business_verification",
        "contacts",
        ["business_id", "verification_status"],
    )
    op.create_index(
        "ix_source_observations_business_observed",
        "source_observations",
        ["business_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_observations_business_observed",
        table_name="source_observations",
    )
    op.drop_index("ix_contacts_business_verification", table_name="contacts")
    op.drop_index(
        "ix_business_niche_memberships_niche_market",
        table_name="business_niche_memberships",
    )
    op.drop_index("ix_businesses_status_market_category", table_name="businesses")
    if sa.inspect(op.get_bind()).has_table("business_index_segments"):
        op.drop_table("business_index_segments")
