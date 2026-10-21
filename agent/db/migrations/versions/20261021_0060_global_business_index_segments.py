"""remove product ownership from shared business index segments

Revision ID: 20261021_0060
Revises: 20261020_0059
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20261021_0060"
down_revision = "20261020_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_index_segments"):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("business_index_segments")
    }
    if "product_id" not in columns:
        return

    for foreign_key in inspector.get_foreign_keys("business_index_segments"):
        if foreign_key.get("constrained_columns") != ["product_id"]:
            continue
        constraint_name = foreign_key.get("name")
        if constraint_name:
            op.drop_constraint(
                constraint_name,
                "business_index_segments",
                type_="foreignkey",
            )

    indexes = {
        index["name"]
        for index in inspector.get_indexes("business_index_segments")
    }
    if "ix_business_index_segments_product_id" in indexes:
        op.drop_index(
            "ix_business_index_segments_product_id",
            table_name="business_index_segments",
        )

    op.drop_column("business_index_segments", "product_id")


def downgrade() -> None:
    raise RuntimeError(
        "Product ownership cannot be reconstructed for globally shared index segments"
    )
