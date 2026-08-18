"""add product source draft cache

Revision ID: 20260818_0004
Revises: 20260818_0003
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0004"
down_revision = "20260818_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("product_source_drafts"):
        return

    op.create_table(
        "product_source_drafts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("context_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("target_geography", sa.String(length=255), nullable=False),
        sa.Column("inference", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_fingerprint",
            "context_fingerprint",
            name="uq_product_source_drafts_source_context",
        ),
    )
    op.create_index(
        "ix_product_source_drafts_source_fingerprint",
        "product_source_drafts",
        ["source_fingerprint"],
    )
    op.create_index(
        "ix_product_source_drafts_context_fingerprint",
        "product_source_drafts",
        ["context_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_source_drafts_context_fingerprint", table_name="product_source_drafts")
    op.drop_index("ix_product_source_drafts_source_fingerprint", table_name="product_source_drafts")
    op.drop_table("product_source_drafts")
