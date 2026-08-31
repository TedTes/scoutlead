"""add lead review state

Revision ID: 20260831_0009
Revises: 20260820_0008
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "20260831_0009"
down_revision = "20260820_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "review_status" not in columns:
        op.add_column(
            "leads",
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default="unreviewed"),
        )
        op.alter_column("leads", "review_status", server_default=None)
    if "review_note" not in columns:
        op.add_column("leads", sa.Column("review_note", sa.Text(), nullable=True))
    if "reviewed_at" not in columns:
        op.add_column("leads", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    if "shortlisted_at" not in columns:
        op.add_column("leads", sa.Column("shortlisted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("leads")}
    if "shortlisted_at" in columns:
        op.drop_column("leads", "shortlisted_at")
    if "reviewed_at" in columns:
        op.drop_column("leads", "reviewed_at")
    if "review_note" in columns:
        op.drop_column("leads", "review_note")
    if "review_status" in columns:
        op.drop_column("leads", "review_status")
