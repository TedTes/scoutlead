"""add semantic cache fields to canonical businesses

Revision ID: 20260903_0014
Revises: 20260903_0013
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_0014"
down_revision = "20260903_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("businesses"):
        return

    dialect = bind.dialect.name
    existing_columns = {column["name"] for column in inspector.get_columns("businesses")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("businesses")}

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    if "category_key" not in existing_columns:
        op.add_column("businesses", sa.Column("category_key", sa.String(length=255), nullable=True))
    if "market_key" not in existing_columns:
        op.add_column("businesses", sa.Column("market_key", sa.String(length=255), nullable=True))
    if "semantic_text" not in existing_columns:
        op.add_column("businesses", sa.Column("semantic_text", sa.Text(), nullable=True))
    if "embedding" not in existing_columns:
        if dialect == "postgresql":
            op.execute("ALTER TABLE businesses ADD COLUMN IF NOT EXISTS embedding vector(1536)")
    else:
        op.add_column("businesses", sa.Column("embedding", sa.JSON(), nullable=True))
    if "embedding_model" not in existing_columns:
        op.add_column(
            "businesses",
            sa.Column("embedding_model", sa.String(length=255), nullable=True),
        )
    if "embedding_updated_at" not in existing_columns:
        op.add_column(
            "businesses",
            sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "ix_businesses_category_key" not in existing_indexes:
        op.create_index("ix_businesses_category_key", "businesses", ["category_key"], unique=False)
    if "ix_businesses_market_key" not in existing_indexes:
        op.create_index("ix_businesses_market_key", "businesses", ["market_key"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("businesses"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("businesses")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("businesses")}

    if "ix_businesses_market_key" in existing_indexes:
        op.drop_index("ix_businesses_market_key", table_name="businesses")
    if "ix_businesses_category_key" in existing_indexes:
        op.drop_index("ix_businesses_category_key", table_name="businesses")

    for column_name in (
        "embedding_updated_at",
        "embedding_model",
        "embedding",
        "semantic_text",
        "market_key",
        "category_key",
    ):
        if column_name in existing_columns:
            op.drop_column("businesses", column_name)
