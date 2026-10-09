"""separate audience runs from outreach campaigns

Revision ID: 20261008_0038
Revises: 20261008_0037
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0038"
down_revision = "20261008_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audience_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=255), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("audience_id", sa.String(length=64), sa.ForeignKey("territories.id"), nullable=False),
        sa.Column("criteria_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("new_result_count", sa.Integer(), nullable=False),
        sa.Column("index_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    _indexes("audience_runs", ["workspace_id", "audience_id", "state"])
    op.create_index("ix_audience_runs_audience_created", "audience_runs", ["audience_id", "created_at"])
    op.create_index("ix_audience_runs_state_deadline", "audience_runs", ["state", "deadline_at"])

    op.create_table(
        "audience_results",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("audience_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audience_id", sa.String(length=64), sa.ForeignKey("territories.id"), nullable=False),
        sa.Column("business_id", sa.String(length=64), sa.ForeignKey("businesses.id"), nullable=False),
        sa.Column("publication_id", sa.String(length=64), sa.ForeignKey("business_publications.id"), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("match_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "business_id", name="uq_audience_results_run_business"),
        sa.UniqueConstraint("run_id", "rank_position", name="uq_audience_results_run_rank"),
    )
    _indexes("audience_results", ["run_id", "audience_id", "business_id", "publication_id"])

    op.create_table(
        "coverage_requests",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("audience_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audience_id", sa.String(length=64), sa.ForeignKey("territories.id"), nullable=False),
        sa.Column("niche_id", sa.String(length=64), sa.ForeignKey("niches.id"), nullable=False),
        sa.Column("market_key", sa.String(length=255), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "niche_id", name="uq_coverage_requests_run_niche"),
    )
    _indexes("coverage_requests", ["run_id", "audience_id", "niche_id", "market_key", "status"])
    op.create_index("ix_coverage_requests_status_created", "coverage_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("coverage_requests")
    op.drop_table("audience_results")
    op.drop_table("audience_runs")


def _indexes(table: str, columns: list[str]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
