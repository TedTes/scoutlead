"""add evidence, publication, and quality control tables

Revision ID: 20261008_0037
Revises: 20261008_0036
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0037"
down_revision = "20261008_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "business_facts",
        sa.Column(
            "resolution_state",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "business_facts",
        sa.Column("supporting_claim_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "business_facts",
        sa.Column(
            "quality_state",
            sa.String(length=32),
            nullable=False,
            server_default="staged",
        ),
    )
    op.add_column(
        "business_facts",
        sa.Column(
            "quality_policy_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.create_index(
        "ix_business_facts_resolution_state",
        "business_facts",
        ["resolution_state"],
    )
    op.create_index(
        "ix_business_facts_quality_state",
        "business_facts",
        ["quality_state"],
    )
    facts = sa.table(
        "business_facts",
        sa.column("confidence", sa.Integer()),
        sa.column("resolution_state", sa.String()),
    )
    op.execute(
        facts.update().values(
            resolution_state=sa.case(
                (facts.c.confidence >= 90, "confirmed"),
                (facts.c.confidence > 0, "probable"),
                else_="unknown",
            )
        )
    )
    op.alter_column("business_facts", "resolution_state", server_default=None)
    op.alter_column("business_facts", "supporting_claim_ids", server_default=None)
    op.alter_column("business_facts", "quality_state", server_default=None)
    op.alter_column("business_facts", "quality_policy_version", server_default=None)

    op.create_table(
        "fact_claims",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("fact_key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("source_observation_id", sa.String(length=64), sa.ForeignKey("source_observations.id"), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(length=128), nullable=False),
        sa.Column("extractor_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("fact_claims", ["business_id", "fact_key", "source_observation_id"])
    op.create_index("ix_fact_claims_business_key_observed", "fact_claims", ["business_id", "fact_key", "observed_at"])

    op.create_table(
        "validation_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("source_item_id", sa.String(length=64), sa.ForeignKey("source_items.id"), nullable=True),
        sa.Column(
            "source_observation_id",
            sa.String(length=64),
            sa.ForeignKey("source_observations.id"),
            nullable=True,
        ),
        sa.Column("niche_id", sa.String(length=64), sa.ForeignKey("niches.id"), nullable=True),
        sa.Column("market_key", sa.String(length=255), nullable=True),
        sa.Column("validation_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("validator", sa.String(length=128), nullable=False),
        sa.Column("validator_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes(
        "validation_results",
        [
            "business_id",
            "source_item_id",
            "source_observation_id",
            "niche_id",
            "market_key",
            "validation_type",
            "status",
        ],
    )
    op.create_index("ix_validation_results_business_type_observed", "validation_results", ["business_id", "validation_type", "observed_at"])

    op.create_table(
        "business_publications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("niche_id", sa.String(length=64), sa.ForeignKey("niches.id"), nullable=False),
        sa.Column("market_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("business_id", "niche_id", "market_key", name="uq_business_publications_scope"),
    )
    _indexes("business_publications", ["business_id", "niche_id", "market_key", "status"])
    op.create_index("ix_business_publications_scope_status", "business_publications", ["niche_id", "market_key", "status"])

    op.create_table(
        "quality_labels",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=True, unique=True),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False),
        sa.Column("predicted", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("niche_id", sa.String(length=64), sa.ForeignKey("niches.id"), nullable=True),
        sa.Column("market_key", sa.String(length=255), nullable=True),
        sa.Column("validator_version", sa.Integer(), nullable=True),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("quality_labels", ["business_id", "dimension", "source", "niche_id", "market_key"])
    op.create_index("ix_quality_labels_dimension_reviewed", "quality_labels", ["dimension", "reviewed_at"])
    op.create_index("ix_quality_labels_scope", "quality_labels", ["source", "niche_id", "market_key"])

    op.create_table(
        "quality_metric_snapshots",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("niche_id", sa.String(length=64), sa.ForeignKey("niches.id"), nullable=True),
        sa.Column("market_key", sa.String(length=255), nullable=True),
        sa.Column("validator_version", sa.Integer(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("true_positive", sa.Integer(), nullable=False),
        sa.Column("false_positive", sa.Integer(), nullable=False),
        sa.Column("false_negative", sa.Integer(), nullable=False),
        sa.Column("true_negative", sa.Integer(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("precision_lower_bound", sa.Float(), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("quality_metric_snapshots", ["dimension", "source", "niche_id", "market_key"])
    op.create_index("ix_quality_metrics_dimension_calculated", "quality_metric_snapshots", ["dimension", "calculated_at"])
    op.create_index("ix_quality_metrics_scope", "quality_metric_snapshots", ["source", "niche_id", "market_key"])

    op.create_table(
        "pipeline_outbox_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("pipeline_outbox_events", ["topic", "aggregate_id", "status"])
    op.create_index("ix_pipeline_outbox_poll", "pipeline_outbox_events", ["status", "available_at", "created_at"])


def downgrade() -> None:
    for table in (
        "pipeline_outbox_events",
        "quality_metric_snapshots",
        "quality_labels",
        "business_publications",
        "validation_results",
        "fact_claims",
    ):
        op.drop_table(table)
    op.drop_index("ix_business_facts_resolution_state", table_name="business_facts")
    op.drop_index("ix_business_facts_quality_state", table_name="business_facts")
    op.drop_column("business_facts", "quality_policy_version")
    op.drop_column("business_facts", "quality_state")
    op.drop_column("business_facts", "supporting_claim_ids")
    op.drop_column("business_facts", "resolution_state")


def _indexes(table: str, columns: list[str]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
