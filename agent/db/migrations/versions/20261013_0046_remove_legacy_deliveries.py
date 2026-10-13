"""remove the legacy territory delivery pipeline

Revision ID: 20261013_0046
Revises: 20261013_0045
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_0046"
down_revision = "20261013_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("queue_jobs"):
        bind.execute(
            sa.text("DELETE FROM queue_jobs WHERE type = 'territory.refresh'")
        )
    if inspector.has_table("profile_delivery_items"):
        op.drop_table("profile_delivery_items")
    if inspector.has_table("territory_deliveries"):
        op.drop_table("territory_deliveries")


def downgrade() -> None:
    op.create_table(
        "territory_deliveries",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("territory_id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_contact_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("campaign_id", name="uq_territory_deliveries_campaign_id"),
        sa.UniqueConstraint(
            "territory_id",
            "scheduled_for",
            name="uq_territory_deliveries_territory_schedule",
        ),
    )
    for column in ("workspace_id", "territory_id", "campaign_id", "status"):
        op.create_index(
            op.f(f"ix_territory_deliveries_{column}"),
            "territory_deliveries",
            [column],
        )
    op.create_table(
        "profile_delivery_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["delivery_id"], ["territory_deliveries.id"]),
        sa.ForeignKeyConstraint(["profile_id"], ["territories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id",
            "business_id",
            name="uq_profile_delivery_items_profile_business",
        ),
        sa.UniqueConstraint(
            "delivery_id",
            "business_id",
            name="uq_profile_delivery_items_delivery_business",
        ),
    )
    for column in ("profile_id", "delivery_id", "business_id"):
        op.create_index(
            op.f(f"ix_profile_delivery_items_{column}"),
            "profile_delivery_items",
            [column],
        )
