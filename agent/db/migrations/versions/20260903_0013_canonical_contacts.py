"""add canonical businesses and contacts

Revision ID: 20260903_0013
Revises: 20260902_0012
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_0013"
down_revision = "20260902_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("businesses"):
        op.create_table(
            "businesses",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("website_url", sa.String(length=1000), nullable=True),
            sa.Column("domain", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("geography", sa.String(length=255), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "normalized_name",
                "domain",
                name="uq_businesses_normalized_name_domain",
            ),
        )
        op.create_index(op.f("ix_businesses_domain"), "businesses", ["domain"], unique=False)
        op.create_index(op.f("ix_businesses_geography"), "businesses", ["geography"], unique=False)
        op.create_index(
            op.f("ix_businesses_normalized_name"),
            "businesses",
            ["normalized_name"],
            unique=False,
        )

    if not inspector.has_table("contacts"):
        op.create_table(
            "contacts",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("business_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("phone", sa.String(length=64), nullable=True),
            sa.Column("verification_status", sa.String(length=32), nullable=False),
            sa.Column("verification_provider", sa.String(length=255), nullable=True),
            sa.Column("verification_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verification_reason", sa.Text(), nullable=True),
            sa.Column("verification_score", sa.Integer(), nullable=True),
            sa.Column("verification_details", sa.JSON(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("business_id", "email", name="uq_contacts_business_email"),
        )
        op.create_index(op.f("ix_contacts_business_id"), "contacts", ["business_id"], unique=False)
        op.create_index(op.f("ix_contacts_email"), "contacts", ["email"], unique=False)
        op.create_index(op.f("ix_contacts_phone"), "contacts", ["phone"], unique=False)

    if not inspector.has_table("source_observations"):
        op.create_table(
            "source_observations",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("business_id", sa.String(length=64), nullable=False),
            sa.Column("source", sa.String(length=255), nullable=False),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("query_signature", sa.String(length=500), nullable=True),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "source",
                "external_id",
                name="uq_source_observations_source_external_id",
            ),
        )
        op.create_index(
            op.f("ix_source_observations_business_id"),
            "source_observations",
            ["business_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_source_observations_content_hash"),
            "source_observations",
            ["content_hash"],
            unique=False,
        )
        op.create_index(
            op.f("ix_source_observations_external_id"),
            "source_observations",
            ["external_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_source_observations_query_signature"),
            "source_observations",
            ["query_signature"],
            unique=False,
        )
        op.create_index(
            op.f("ix_source_observations_source"),
            "source_observations",
            ["source"],
            unique=False,
        )

    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "business_id" not in lead_columns:
        op.add_column(
            "leads",
            sa.Column(
                "business_id",
                sa.String(length=64),
                sa.ForeignKey("businesses.id"),
                nullable=True,
            ),
        )
        op.create_index(op.f("ix_leads_business_id"), "leads", ["business_id"], unique=False)
    if "contact_id" not in lead_columns:
        op.add_column(
            "leads",
            sa.Column(
                "contact_id",
                sa.String(length=64),
                sa.ForeignKey("contacts.id"),
                nullable=True,
            ),
        )
        op.create_index(op.f("ix_leads_contact_id"), "leads", ["contact_id"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    lead_columns = {column["name"] for column in inspector.get_columns("leads")}
    if "contact_id" in lead_columns:
        op.drop_index(op.f("ix_leads_contact_id"), table_name="leads")
        op.drop_column("leads", "contact_id")
    if "business_id" in lead_columns:
        op.drop_index(op.f("ix_leads_business_id"), table_name="leads")
        op.drop_column("leads", "business_id")

    if inspector.has_table("source_observations"):
        op.drop_index(op.f("ix_source_observations_source"), table_name="source_observations")
        op.drop_index(
            op.f("ix_source_observations_query_signature"),
            table_name="source_observations",
        )
        op.drop_index(op.f("ix_source_observations_external_id"), table_name="source_observations")
        op.drop_index(op.f("ix_source_observations_content_hash"), table_name="source_observations")
        op.drop_index(op.f("ix_source_observations_business_id"), table_name="source_observations")
        op.drop_table("source_observations")

    if inspector.has_table("contacts"):
        op.drop_index(op.f("ix_contacts_phone"), table_name="contacts")
        op.drop_index(op.f("ix_contacts_email"), table_name="contacts")
        op.drop_index(op.f("ix_contacts_business_id"), table_name="contacts")
        op.drop_table("contacts")

    if inspector.has_table("businesses"):
        op.drop_index(op.f("ix_businesses_normalized_name"), table_name="businesses")
        op.drop_index(op.f("ix_businesses_geography"), table_name="businesses")
        op.drop_index(op.f("ix_businesses_domain"), table_name="businesses")
        op.drop_table("businesses")
