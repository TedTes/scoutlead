"""add fact freshness and change history

Revision ID: 20261007_0035
Revises: 20261005_0034
Create Date: 2026-10-07
"""

from datetime import timedelta

from alembic import op
import sqlalchemy as sa


revision = "20261007_0035"
down_revision = "20261005_0034"
branch_labels = None
depends_on = None


TTL_DAYS = {
    "website_status": 30,
    "quote_or_booking_form_present": 30,
    "contact_form_present": 30,
    "google_rating": 14,
    "google_review_count": 14,
    "business_operational": 14,
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_fact_changes"):
        op.create_table(
            "business_fact_changes",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column(
                "business_id",
                sa.String(length=64),
                sa.ForeignKey("businesses.id"),
                nullable=False,
            ),
            sa.Column("fact_key", sa.String(length=128), nullable=False),
            sa.Column("previous_value", sa.JSON(), nullable=True),
            sa.Column("current_value", sa.JSON(), nullable=False),
            sa.Column("previous_confidence", sa.Integer(), nullable=True),
            sa.Column("current_confidence", sa.Integer(), nullable=False),
            sa.Column(
                "source_observation_id",
                sa.String(length=64),
                sa.ForeignKey("source_observations.id"),
                nullable=True,
            ),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_business_fact_changes_business_id",
            "business_fact_changes",
            ["business_id"],
        )
        op.create_index(
            "ix_business_fact_changes_fact_key",
            "business_fact_changes",
            ["fact_key"],
        )
        op.create_index(
            "ix_business_fact_changes_source_observation_id",
            "business_fact_changes",
            ["source_observation_id"],
        )
        op.create_index(
            "ix_business_fact_changes_changed_at",
            "business_fact_changes",
            ["changed_at"],
        )
        op.create_index(
            "ix_business_fact_changes_business_changed",
            "business_fact_changes",
            ["business_id", "changed_at"],
        )
        op.create_index(
            "ix_business_fact_changes_key_changed",
            "business_fact_changes",
            ["fact_key", "changed_at"],
        )

    facts = sa.Table("business_facts", sa.MetaData(), autoload_with=bind)
    for row in bind.execute(
        sa.select(facts.c.id, facts.c.fact_key, facts.c.observed_at, facts.c.expires_at)
    ).mappings():
        if row["expires_at"] is not None:
            continue
        bind.execute(
            facts.update()
            .where(facts.c.id == row["id"])
            .values(
                expires_at=row["observed_at"]
                + timedelta(days=TTL_DAYS.get(row["fact_key"], 30))
            )
        )


def downgrade() -> None:
    op.drop_table("business_fact_changes")
