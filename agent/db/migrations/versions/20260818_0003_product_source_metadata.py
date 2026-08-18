"""add product source metadata

Revision ID: 20260818_0003
Revises: 20260814_0002
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20260818_0003"
down_revision = "20260814_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("products")}

    if "source_url" not in columns:
        op.add_column("products", sa.Column("source_url", sa.String(length=1000), nullable=True))
    if "source_fingerprint" not in columns:
        op.add_column(
            "products", sa.Column("source_fingerprint", sa.String(length=255), nullable=True)
        )
    if "source_last_checked_at" not in columns:
        op.add_column(
            "products", sa.Column("source_last_checked_at", sa.DateTime(timezone=True), nullable=True)
        )
    if "source_evidence" not in columns:
        op.add_column("products", sa.Column("source_evidence", sa.JSON(), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("products")}
    if "ix_products_source_fingerprint" not in indexes:
        op.create_index(
            "ix_products_source_fingerprint",
            "products",
            ["source_fingerprint"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index("ix_products_source_fingerprint", table_name="products")
    op.drop_column("products", "source_evidence")
    op.drop_column("products", "source_last_checked_at")
    op.drop_column("products", "source_fingerprint")
    op.drop_column("products", "source_url")
