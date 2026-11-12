"""drop the retired business publications compatibility table

Revision ID: 20261112_0087
Revises: 20261112_0086
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op


revision = "20261112_0087"
down_revision = "20261112_0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("business_publications"):
        op.drop_table("business_publications")


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("business_publications"):
        return

    op.create_table(
        "business_publications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "business_id",
            sa.String(length=64),
            sa.ForeignKey("businesses.id"),
            nullable=False,
        ),
        sa.Column(
            "niche_id",
            sa.String(length=64),
            sa.ForeignKey("niches.id"),
            nullable=False,
        ),
        sa.Column("market_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "business_id",
            "niche_id",
            "market_key",
            name="uq_business_publications_scope",
        ),
    )
    op.create_index(
        "ix_business_publications_business_id",
        "business_publications",
        ["business_id"],
    )
    op.create_index(
        "ix_business_publications_niche_id",
        "business_publications",
        ["niche_id"],
    )
    op.create_index(
        "ix_business_publications_market_key",
        "business_publications",
        ["market_key"],
    )
    op.create_index(
        "ix_business_publications_status",
        "business_publications",
        ["status"],
    )
    op.create_index(
        "ix_business_publications_scope_status",
        "business_publications",
        ["niche_id", "market_key", "status"],
    )
