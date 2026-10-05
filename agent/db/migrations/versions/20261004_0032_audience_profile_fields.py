"""add audience profile fields to territories

Revision ID: 20261004_0032
Revises: 20261002_0031
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20261004_0032"
down_revision = "20261002_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("territories"):
        return
    columns = {column["name"] for column in inspector.get_columns("territories")}
    additions = [
        ("city", sa.Column("city", sa.String(length=255), nullable=False, server_default="")),
        ("latitude", sa.Column("latitude", sa.Float(), nullable=True)),
        ("longitude", sa.Column("longitude", sa.Float(), nullable=True)),
        ("radius_km", sa.Column("radius_km", sa.Integer(), nullable=False, server_default="25")),
        ("trade_keys", sa.Column("trade_keys", sa.JSON(), nullable=False, server_default="[]")),
        (
            "customer_kind",
            sa.Column(
                "customer_kind",
                sa.String(length=32),
                nullable=False,
                server_default="residential",
            ),
        ),
        ("signal_keys", sa.Column("signal_keys", sa.JSON(), nullable=False, server_default="[]")),
        (
            "exclusion_keys",
            sa.Column("exclusion_keys", sa.JSON(), nullable=False, server_default="[]"),
        ),
        (
            "refill_policy",
            sa.Column(
                "refill_policy",
                sa.String(length=32),
                nullable=False,
                server_default="when_depleted",
            ),
        ),
        (
            "criteria_version",
            sa.Column("criteria_version", sa.Integer(), nullable=False, server_default="1"),
        ),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("territories", column)
    bind.execute(sa.text("UPDATE territories SET city = market_key WHERE city = ''"))
    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("territories")}
    if "ix_territories_refill_policy" not in index_names:
        op.create_index("ix_territories_refill_policy", "territories", ["refill_policy"])
    if "ix_territories_customer_kind" not in index_names:
        op.create_index("ix_territories_customer_kind", "territories", ["customer_kind"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("territories"):
        return
    index_names = {index["name"] for index in inspector.get_indexes("territories")}
    if "ix_territories_refill_policy" in index_names:
        op.drop_index("ix_territories_refill_policy", table_name="territories")
    if "ix_territories_customer_kind" in index_names:
        op.drop_index("ix_territories_customer_kind", table_name="territories")
    columns = {column["name"] for column in inspector.get_columns("territories")}
    for name in (
        "criteria_version",
        "refill_policy",
        "exclusion_keys",
        "signal_keys",
        "customer_kind",
        "trade_keys",
        "radius_km",
        "longitude",
        "latitude",
        "city",
    ):
        if name in columns:
            op.drop_column("territories", name)
