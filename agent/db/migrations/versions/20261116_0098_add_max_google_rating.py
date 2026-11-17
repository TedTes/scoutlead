"""add maximum Google rating to saved-search filters

Revision ID: 20261116_0098
Revises: 20261113_0097
Create Date: 2026-11-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20261116_0098"
down_revision = "20261113_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("territories")
    }
    if "max_google_rating" not in columns:
        op.add_column(
            "territories",
            sa.Column("max_google_rating", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("territories")
    }
    if "max_google_rating" not in columns:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("territories") as batch_op:
            batch_op.drop_column("max_google_rating")
    else:
        op.drop_column("territories", "max_google_rating")
