"""drop retired quality, insights, demo, draft-cache, and summary tables

Revision ID: 20261020_0057
Revises: 20261020_0056
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0057"
down_revision = "20261020_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("demo_sites")
    op.drop_table("quality_metric_snapshots")
    op.drop_table("quality_labels")
    op.drop_table("campaign_insights")
    op.drop_table("product_source_drafts")
    op.drop_table("learning_summaries")


def downgrade() -> None:
    op.create_table(
        "learning_summaries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("product_id", sa.String(length=64), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learning_summaries_product_id", "learning_summaries", ["product_id"])

    op.create_table(
        "product_source_drafts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("context_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("target_geography", sa.String(length=255), nullable=False),
        sa.Column("inference", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_fingerprint",
            "context_fingerprint",
            name="uq_product_source_drafts_source_context",
        ),
    )
    op.create_index(
        "ix_product_source_drafts_source_fingerprint",
        "product_source_drafts",
        ["source_fingerprint"],
    )
    op.create_index(
        "ix_product_source_drafts_context_fingerprint",
        "product_source_drafts",
        ["context_fingerprint"],
    )

    op.create_table(
        "campaign_insights",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("product_id", sa.String(length=64), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("goal_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("icp_verdict", sa.JSON(), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaign_insights_campaign_id", "campaign_insights", ["campaign_id"])
    op.create_index("ix_campaign_insights_product_id", "campaign_insights", ["product_id"])

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
    for column in ("business_id", "dimension", "source", "niche_id", "market_key"):
        op.create_index(f"ix_quality_labels_{column}", "quality_labels", [column])
    op.create_index(
        "ix_quality_labels_dimension_reviewed",
        "quality_labels",
        ["dimension", "reviewed_at"],
    )
    op.create_index(
        "ix_quality_labels_scope",
        "quality_labels",
        ["source", "niche_id", "market_key"],
    )

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
    for column in ("dimension", "source", "niche_id", "market_key"):
        op.create_index(
            f"ix_quality_metric_snapshots_{column}",
            "quality_metric_snapshots",
            [column],
        )
    op.create_index(
        "ix_quality_metrics_dimension_calculated",
        "quality_metric_snapshots",
        ["dimension", "calculated_at"],
    )
    op.create_index(
        "ix_quality_metrics_scope",
        "quality_metric_snapshots",
        ["source", "niche_id", "market_key"],
    )

    op.create_table(
        "demo_sites",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=255), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column(
            "audience_result_id",
            sa.String(length=64),
            sa.ForeignKey("audience_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("share_token", sa.String(length=96), nullable=False, unique=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("outreach_message", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id",
            "audience_result_id",
            name="uq_demo_sites_workspace_result",
        ),
    )
    for column in (
        "workspace_id",
        "audience_result_id",
        "business_id",
        "share_token",
        "status",
    ):
        op.create_index(f"ix_demo_sites_{column}", "demo_sites", [column])

