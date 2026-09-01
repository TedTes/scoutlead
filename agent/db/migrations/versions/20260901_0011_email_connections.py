"""add email connections

Revision ID: 20260901_0011
Revises: 20260831_0010
Create Date: 2026-09-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_0011"
down_revision = "20260831_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("email_connections"):
        return

    op.create_table(
        "email_connections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "provider", name="uq_email_connections_product_provider"),
    )
    op.create_index(
        op.f("ix_email_connections_product_id"),
        "email_connections",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_connections_provider"),
        "email_connections",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("email_connections"):
        return

    op.drop_index(op.f("ix_email_connections_provider"), table_name="email_connections")
    op.drop_index(op.f("ix_email_connections_product_id"), table_name="email_connections")
    op.drop_table("email_connections")
