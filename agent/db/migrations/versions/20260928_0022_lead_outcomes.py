"""add lead outcomes and latest outcome fields

Revision ID: 20260928_0022
Revises: 20260928_0021
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0022"
down_revision = "20260928_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("businesses") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active")
        )
        batch_op.create_index("ix_businesses_status", ["status"])
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("latest_outcome", sa.String(length=32)))
        batch_op.add_column(sa.Column("latest_outcome_at", sa.DateTime(timezone=True)))
        batch_op.create_index("ix_leads_latest_outcome", ["latest_outcome"])
    op.create_table(
        "lead_outcomes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64)),
        sa.Column("territory_id", sa.String(length=64)),
        sa.Column("niche_id", sa.String(length=64)),
        sa.Column("market_key", sa.String(length=255)),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "workspace_id",
        "product_id",
        "lead_id",
        "business_id",
        "territory_id",
        "niche_id",
        "market_key",
        "outcome",
        "occurred_at",
    ):
        op.create_index(f"ix_lead_outcomes_{column}", "lead_outcomes", [column])


def downgrade() -> None:
    op.drop_table("lead_outcomes")
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_latest_outcome")
        batch_op.drop_column("latest_outcome_at")
        batch_op.drop_column("latest_outcome")
    with op.batch_alter_table("businesses") as batch_op:
        batch_op.drop_index("ix_businesses_status")
        batch_op.drop_column("status")
