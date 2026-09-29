"""add workspace territories and deliveries

Revision ID: 20260928_0019
Revises: 20260928_0018
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0019"
down_revision = "20260928_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("territories"):
        op.create_table(
            "territories",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workspace_id", sa.String(length=255), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.Column("niche_id", sa.String(length=64), nullable=False),
            sa.Column("market_key", sa.String(length=255), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("cadence", sa.String(length=32), nullable=False),
            sa.Column("batch_size", sa.Integer(), nullable=False),
            sa.Column("min_fit", sa.String(length=32), nullable=False),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id",
                "product_id",
                "niche_id",
                "market_key",
                name="uq_territories_workspace_offer_niche_market",
            ),
        )
        for column_name in ("workspace_id", "product_id", "niche_id", "market_key", "status"):
            op.create_index(op.f(f"ix_territories_{column_name}"), "territories", [column_name])

    inspector = sa.inspect(bind)
    campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "territory_id" not in campaign_columns:
        with op.batch_alter_table("campaigns") as batch_op:
            batch_op.add_column(sa.Column("territory_id", sa.String(length=64), nullable=True))
            batch_op.create_foreign_key(
                "fk_campaigns_territory_id_territories",
                "territories",
                ["territory_id"],
                ["id"],
            )
            batch_op.create_index("ix_campaigns_territory_id", ["territory_id"])

    inspector = sa.inspect(bind)
    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "territory_id" not in lead_columns:
        with op.batch_alter_table("leads") as batch_op:
            batch_op.add_column(sa.Column("territory_id", sa.String(length=64), nullable=True))
            batch_op.create_foreign_key(
                "fk_leads_territory_id_territories",
                "territories",
                ["territory_id"],
                ["id"],
            )
            batch_op.create_index("ix_leads_territory_id", ["territory_id"])
        bind.execute(
            sa.text(
                "UPDATE leads SET territory_id = campaigns.territory_id "
                "FROM campaigns WHERE leads.campaign_id = campaigns.id"
            )
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("territory_deliveries"):
        op.create_table(
            "territory_deliveries",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workspace_id", sa.String(length=255), nullable=False),
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
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["territory_id"], ["territories.id"]),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("campaign_id", name="uq_territory_deliveries_campaign_id"),
            sa.UniqueConstraint(
                "territory_id",
                "scheduled_for",
                name="uq_territory_deliveries_territory_schedule",
            ),
        )
        for column_name in ("workspace_id", "territory_id", "campaign_id", "status"):
            op.create_index(
                op.f(f"ix_territory_deliveries_{column_name}"),
                "territory_deliveries",
                [column_name],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("territory_deliveries"):
        for column_name in ("status", "campaign_id", "territory_id", "workspace_id"):
            op.drop_index(
                op.f(f"ix_territory_deliveries_{column_name}"),
                table_name="territory_deliveries",
            )
        op.drop_table("territory_deliveries")

    inspector = sa.inspect(bind)
    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "territory_id" in lead_columns:
        with op.batch_alter_table("leads") as batch_op:
            batch_op.drop_index("ix_leads_territory_id")
            batch_op.drop_constraint(
                "fk_leads_territory_id_territories",
                type_="foreignkey",
            )
            batch_op.drop_column("territory_id")

    inspector = sa.inspect(bind)
    campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    if "territory_id" in campaign_columns:
        with op.batch_alter_table("campaigns") as batch_op:
            batch_op.drop_index("ix_campaigns_territory_id")
            batch_op.drop_constraint(
                "fk_campaigns_territory_id_territories",
                type_="foreignkey",
            )
            batch_op.drop_column("territory_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("territories"):
        for column_name in ("status", "market_key", "niche_id", "product_id", "workspace_id"):
            op.drop_index(op.f(f"ix_territories_{column_name}"), table_name="territories")
        op.drop_table("territories")
