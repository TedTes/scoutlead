"""persist campaign source inputs

Revision ID: 20260930_0025
Revises: 20260928_0024
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260930_0025"
down_revision = "20260928_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("campaigns")}
    with op.batch_alter_table("campaigns") as batch_op:
        if "source_input" not in columns:
            batch_op.add_column(sa.Column("source_input", sa.Text(), nullable=True))
        if "source_inputs" not in columns:
            batch_op.add_column(
                sa.Column(
                    "source_inputs",
                    sa.JSON(),
                    nullable=False,
                    server_default=sa.text("'{}'"),
                )
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("campaigns")}
    with op.batch_alter_table("campaigns") as batch_op:
        if "source_inputs" in columns:
            batch_op.drop_column("source_inputs")
        if "source_input" in columns:
            batch_op.drop_column("source_input")
