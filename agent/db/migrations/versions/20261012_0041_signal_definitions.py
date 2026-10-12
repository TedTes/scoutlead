"""add dynamic observable signal definitions

Revision ID: 20261012_0041
Revises: 20261010_0040
Create Date: 2026-10-12
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261012_0041"
down_revision = "20261010_0040"
branch_labels = None
depends_on = None


INITIAL_SIGNALS = (
    ("signal_website_status", "website_status", "Website status", "text", "website", None, "website_http", "website_status", 30, "missing_is_opportunity", {"opportunity_values": ["missing", "not_listed", "unavailable", "parked"]}),
    ("signal_quote_or_booking_form_present", "quote_or_booking_form_present", "Quote or booking form present", "boolean", "conversion", None, "website_dom", "quote_or_booking_form", 30, "false_is_opportunity", {}),
    ("signal_contact_form_present", "contact_form_present", "Contact form present", "boolean", "conversion", None, "website_dom", "contact_form", 30, "false_is_opportunity", {}),
    ("signal_google_rating", "google_rating", "Google rating", "number", "reputation", "stars", "google_places", "google_rating", 14, "lower_is_opportunity", {"opportunity_threshold": 4.3}),
    ("signal_google_review_count", "google_review_count", "Google review count", "number", "reputation", "reviews", "google_places", "google_review_count", 14, "lower_is_opportunity", {"opportunity_threshold": 15}),
    ("signal_business_operational", "business_operational", "Business operational", "boolean", "business", None, "google_places", "business_operational", 14, "none", {}),
    ("signal_domain_age_days", "domain_age_days", "Domain age", "number", "website", "days", "domain_rdap", "domain_age_days", 90, "none", {}),
)


def upgrade() -> None:
    op.create_table(
        "signal_definitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("collector_key", sa.String(length=128), nullable=True),
        sa.Column("extractor_key", sa.String(length=128), nullable=True),
        sa.Column("freshness_days", sa.Integer(), nullable=False),
        sa.Column("opportunity_direction", sa.String(length=32), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_signal_definitions_key"),
    )
    for column in ("key", "category", "status", "collector_key", "extractor_key"):
        op.create_index(f"ix_signal_definitions_{column}", "signal_definitions", [column])
    op.create_index(
        "ix_signal_definitions_status_category",
        "signal_definitions",
        ["status", "category"],
    )

    for table in ("fact_claims", "business_facts"):
        op.add_column(
            table,
            sa.Column("signal_definition_id", sa.String(length=64), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_signal_definition_id",
            table,
            "signal_definitions",
            ["signal_definition_id"],
            ["id"],
        )
        op.create_index(
            f"ix_{table}_signal_definition_id", table, ["signal_definition_id"]
        )

    now = datetime.now(timezone.utc)
    definitions = sa.table(
        "signal_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("value_type", sa.String),
        sa.column("category", sa.String),
        sa.column("unit", sa.String),
        sa.column("status", sa.String),
        sa.column("collector_key", sa.String),
        sa.column("extractor_key", sa.String),
        sa.column("freshness_days", sa.Integer),
        sa.column("opportunity_direction", sa.String),
        sa.column("config", sa.JSON),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        definitions,
        [
            {
                "id": signal_id,
                "key": key,
                "label": label,
                "description": None,
                "value_type": value_type,
                "category": category,
                "unit": unit,
                "status": "active",
                "collector_key": collector,
                "extractor_key": extractor,
                "freshness_days": freshness_days,
                "opportunity_direction": direction,
                "config": config,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for (
                signal_id,
                key,
                label,
                value_type,
                category,
                unit,
                collector,
                extractor,
                freshness_days,
                direction,
                config,
            ) in INITIAL_SIGNALS
        ],
    )

    connection = op.get_bind()
    for signal_id, key, *_rest in INITIAL_SIGNALS:
        for table in ("fact_claims", "business_facts"):
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET signal_definition_id = :signal_id "
                    "WHERE fact_key = :fact_key"
                ),
                {"signal_id": signal_id, "fact_key": key},
            )


def downgrade() -> None:
    for table in ("business_facts", "fact_claims"):
        op.drop_index(f"ix_{table}_signal_definition_id", table_name=table)
        op.drop_constraint(
            f"fk_{table}_signal_definition_id", table, type_="foreignkey"
        )
        op.drop_column(table, "signal_definition_id")
    op.drop_table("signal_definitions")
