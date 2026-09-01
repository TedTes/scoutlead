"""add lead contact verification state

Revision ID: 20260831_0010
Revises: 20260831_0009
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_0010"
down_revision = "20260831_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "verification_status" not in columns:
        op.add_column(
            "leads",
            sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="unverified"),
        )
        op.alter_column("leads", "verification_status", server_default=None)
    if "verification_provider" not in columns:
        op.add_column("leads", sa.Column("verification_provider", sa.String(length=255), nullable=True))
    if "verification_checked_at" not in columns:
        op.add_column("leads", sa.Column("verification_checked_at", sa.DateTime(timezone=True), nullable=True))
    if "verification_reason" not in columns:
        op.add_column("leads", sa.Column("verification_reason", sa.Text(), nullable=True))
    if "verification_score" not in columns:
        op.add_column("leads", sa.Column("verification_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "verification_score" in columns:
        op.drop_column("leads", "verification_score")
    if "verification_reason" in columns:
        op.drop_column("leads", "verification_reason")
    if "verification_checked_at" in columns:
        op.drop_column("leads", "verification_checked_at")
    if "verification_provider" in columns:
        op.drop_column("leads", "verification_provider")
    if "verification_status" in columns:
        op.drop_column("leads", "verification_status")
