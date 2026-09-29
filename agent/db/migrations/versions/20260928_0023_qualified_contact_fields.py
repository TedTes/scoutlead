"""add controlled niche signals and lead approach

Revision ID: 20260928_0023
Revises: 20260928_0022
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0023"
down_revision = "20260928_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("niches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "signal_vocabulary",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("approach", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_column("approach")
    with op.batch_alter_table("niches") as batch_op:
        batch_op.drop_column("signal_vocabulary")
