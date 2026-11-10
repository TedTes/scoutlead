"""add audience rating, review-count, and customer filters

Revision ID: 20261110_0083
Revises: 20261110_0082
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20261110_0083"
down_revision = "20261110_0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("territories")}
    additions = (
        ("min_google_rating", sa.Float()),
        ("min_review_count", sa.Integer()),
        ("max_review_count", sa.Integer()),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column(
                "territories",
                sa.Column(name, column_type, nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("territories")}
    names = [
        name
        for name in ("max_review_count", "min_review_count", "min_google_rating")
        if name in columns
    ]
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("territories") as batch_op:
            for name in names:
                batch_op.drop_column(name)
    else:
        for name in names:
            op.drop_column("territories", name)
