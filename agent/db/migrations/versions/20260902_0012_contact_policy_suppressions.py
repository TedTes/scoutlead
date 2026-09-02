"""add contact policy suppressions

Revision ID: 20260902_0012
Revises: 20260901_0011
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0012"
down_revision = "20260901_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "webhook_url" not in product_columns:
        op.add_column("products", sa.Column("webhook_url", sa.String(length=1000), nullable=True))
    if "webhook_enabled" not in product_columns:
        op.add_column(
            "products",
            sa.Column("webhook_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("products", "webhook_enabled", server_default=None)

    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "contact_policy_status" not in lead_columns:
        op.add_column(
            "leads",
            sa.Column("contact_policy_status", sa.String(length=32), nullable=False, server_default="allowed"),
        )
        op.alter_column("leads", "contact_policy_status", server_default=None)
    if "contact_policy_reason" not in lead_columns:
        op.add_column("leads", sa.Column("contact_policy_reason", sa.Text(), nullable=True))
    if "contact_policy_checked_at" not in lead_columns:
        op.add_column("leads", sa.Column("contact_policy_checked_at", sa.DateTime(timezone=True), nullable=True))
    if "last_contacted_at" not in lead_columns:
        op.add_column("leads", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))
    if "verification_details" not in lead_columns:
        op.add_column("leads", sa.Column("verification_details", sa.JSON(), nullable=True))

    if not inspector.has_table("contact_suppressions"):
        op.create_table(
            "contact_suppressions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=True),
            sa.Column("lead_id", sa.String(length=64), nullable=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("value", sa.String(length=500), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "scope",
                "product_id",
                "kind",
                "value",
                name="uq_contact_suppressions_scope_product_kind_value",
            ),
        )
        op.create_index(op.f("ix_contact_suppressions_kind"), "contact_suppressions", ["kind"], unique=False)
        op.create_index(op.f("ix_contact_suppressions_lead_id"), "contact_suppressions", ["lead_id"], unique=False)
        op.create_index(op.f("ix_contact_suppressions_product_id"), "contact_suppressions", ["product_id"], unique=False)
        op.create_index(op.f("ix_contact_suppressions_scope"), "contact_suppressions", ["scope"], unique=False)
        op.create_index(op.f("ix_contact_suppressions_status"), "contact_suppressions", ["status"], unique=False)
        op.create_index(op.f("ix_contact_suppressions_value"), "contact_suppressions", ["value"], unique=False)

    if not inspector.has_table("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.Column("campaign_id", sa.String(length=64), nullable=False),
            sa.Column("event", sa.String(length=255), nullable=False),
            sa.Column("url", sa.String(length=1000), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("request_payload", sa.JSON(), nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("response_body", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_webhook_deliveries_campaign_id"), "webhook_deliveries", ["campaign_id"], unique=False)
        op.create_index(op.f("ix_webhook_deliveries_product_id"), "webhook_deliveries", ["product_id"], unique=False)
        op.create_index(op.f("ix_webhook_deliveries_status"), "webhook_deliveries", ["status"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("webhook_deliveries"):
        op.drop_index(op.f("ix_webhook_deliveries_status"), table_name="webhook_deliveries")
        op.drop_index(op.f("ix_webhook_deliveries_product_id"), table_name="webhook_deliveries")
        op.drop_index(op.f("ix_webhook_deliveries_campaign_id"), table_name="webhook_deliveries")
        op.drop_table("webhook_deliveries")

    if inspector.has_table("contact_suppressions"):
        op.drop_index(op.f("ix_contact_suppressions_value"), table_name="contact_suppressions")
        op.drop_index(op.f("ix_contact_suppressions_status"), table_name="contact_suppressions")
        op.drop_index(op.f("ix_contact_suppressions_scope"), table_name="contact_suppressions")
        op.drop_index(op.f("ix_contact_suppressions_product_id"), table_name="contact_suppressions")
        op.drop_index(op.f("ix_contact_suppressions_lead_id"), table_name="contact_suppressions")
        op.drop_index(op.f("ix_contact_suppressions_kind"), table_name="contact_suppressions")
        op.drop_table("contact_suppressions")

    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "verification_details" in lead_columns:
        op.drop_column("leads", "verification_details")
    if "last_contacted_at" in lead_columns:
        op.drop_column("leads", "last_contacted_at")
    if "contact_policy_checked_at" in lead_columns:
        op.drop_column("leads", "contact_policy_checked_at")
    if "contact_policy_reason" in lead_columns:
        op.drop_column("leads", "contact_policy_reason")
    if "contact_policy_status" in lead_columns:
        op.drop_column("leads", "contact_policy_status")

    product_columns = {column["name"] for column in inspector.get_columns("products")}
    if "webhook_enabled" in product_columns:
        op.drop_column("products", "webhook_enabled")
    if "webhook_url" in product_columns:
        op.drop_column("products", "webhook_url")
