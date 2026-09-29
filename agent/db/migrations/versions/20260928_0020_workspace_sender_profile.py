"""add workspace sender profile

Revision ID: 20260928_0020
Revises: 20260928_0019
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0020"
down_revision = "20260928_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("workspaces")}
    with op.batch_alter_table("workspaces") as batch_op:
        if "sender_legal_name" not in columns:
            batch_op.add_column(sa.Column("sender_legal_name", sa.String(length=255)))
        if "sender_mailing_address" not in columns:
            batch_op.add_column(sa.Column("sender_mailing_address", sa.Text()))
        if "sender_contact" not in columns:
            batch_op.add_column(sa.Column("sender_contact", sa.String(length=500)))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("workspaces")}
    with op.batch_alter_table("workspaces") as batch_op:
        for column_name in (
            "sender_contact",
            "sender_mailing_address",
            "sender_legal_name",
        ):
            if column_name in columns:
                batch_op.drop_column(column_name)
