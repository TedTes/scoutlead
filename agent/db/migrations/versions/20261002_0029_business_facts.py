"""add current business facts

Revision ID: 20261002_0029
Revises: 20261002_0028
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0029"
down_revision = "20261002_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("source_items"):
        source_constraints = {
            constraint.get("name")
            for constraint in inspector.get_unique_constraints("source_items")
        }
        if "uq_source_items_segment_provider_content" in source_constraints:
            op.drop_constraint(
                "uq_source_items_segment_provider_content",
                "source_items",
                type_="unique",
            )
    if inspector.has_table("source_observations"):
        observation_constraints = {
            constraint.get("name")
            for constraint in inspector.get_unique_constraints("source_observations")
        }
        if "uq_source_observations_source_external_id" in observation_constraints:
            op.drop_constraint(
                "uq_source_observations_source_external_id",
                "source_observations",
                type_="unique",
            )
    if inspector.has_table("business_facts"):
        return
    op.create_table(
        "business_facts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_observation_id", sa.String(length=64), nullable=True),
        sa.Column("resolver_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(
            ["source_observation_id"], ["source_observations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "fact_key",
            name="uq_business_facts_business_key",
        ),
    )
    op.create_index(
        op.f("ix_business_facts_business_id"),
        "business_facts",
        ["business_id"],
    )
    op.create_index(
        op.f("ix_business_facts_fact_key"),
        "business_facts",
        ["fact_key"],
    )
    op.create_index(
        op.f("ix_business_facts_source_observation_id"),
        "business_facts",
        ["source_observation_id"],
    )
    op.create_index(
        "ix_business_facts_key_text",
        "business_facts",
        ["fact_key", "value_text"],
    )
    op.create_index(
        "ix_business_facts_key_number",
        "business_facts",
        ["fact_key", "value_number"],
    )
    op.create_index(
        "ix_business_facts_key_boolean",
        "business_facts",
        ["fact_key", "value_boolean"],
    )
    op.create_index(
        "ix_business_facts_business_observed",
        "business_facts",
        ["business_id", "observed_at"],
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("business_facts"):
        op.drop_table("business_facts")
