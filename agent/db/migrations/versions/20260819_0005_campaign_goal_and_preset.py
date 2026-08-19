"""add campaign goal type and preset reference

Revision ID: 20260819_0005
Revises: 20260818_0004
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_0005"
down_revision = "20260818_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("campaigns"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "goal_type" not in existing_columns:
        op.add_column("campaigns", sa.Column("goal_type", sa.String(length=32), nullable=True))
        op.execute("UPDATE campaigns SET goal_type = 'learn' WHERE goal_type IS NULL")
    if "icp_preset_id" not in existing_columns:
        op.add_column("campaigns", sa.Column("icp_preset_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("campaigns"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "icp_preset_id" in existing_columns:
        op.drop_column("campaigns", "icp_preset_id")
    if "goal_type" in existing_columns:
        op.drop_column("campaigns", "goal_type")
