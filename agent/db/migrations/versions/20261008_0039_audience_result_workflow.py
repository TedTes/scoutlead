"""add audience result workflow state

Revision ID: 20261008_0039
Revises: 20261008_0038
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0039"
down_revision = "20261008_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audience_runs",
        sa.Column(
            "outreach_campaign_id",
            sa.String(length=64),
            sa.ForeignKey("campaigns.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_audience_runs_outreach_campaign_id",
        "audience_runs",
        ["outreach_campaign_id"],
    )
    op.add_column(
        "audience_results",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="unreviewed",
        ),
    )
    op.add_column(
        "audience_results", sa.Column("review_note", sa.Text(), nullable=True)
    )
    op.add_column(
        "audience_results",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audience_results",
        sa.Column("shortlisted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audience_results",
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audience_results",
        sa.Column(
            "outreach_lead_id",
            sa.String(length=64),
            sa.ForeignKey("leads.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_audience_results_review_status",
        "audience_results",
        ["review_status"],
    )
    op.create_index(
        "ix_audience_results_outreach_lead_id",
        "audience_results",
        ["outreach_lead_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audience_results_outreach_lead_id", table_name="audience_results"
    )
    op.drop_index(
        "ix_audience_results_review_status", table_name="audience_results"
    )
    for column in (
        "outreach_lead_id",
        "contacted_at",
        "shortlisted_at",
        "reviewed_at",
        "review_note",
        "review_status",
    ):
        op.drop_column("audience_results", column)
    op.drop_index(
        "ix_audience_runs_outreach_campaign_id", table_name="audience_runs"
    )
    op.drop_column("audience_runs", "outreach_campaign_id")
