"""add run pipeline events

Revision ID: 20261002_0027
Revises: 20261001_0026
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0027"
down_revision = "20261001_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("run_pipeline_events"):
        return
    op.create_table(
        "run_pipeline_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=True),
        sa.Column("job_id", sa.String(length=64), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=True),
        sa.Column("business_id", sa.String(length=64), nullable=True),
        sa.Column("lead_id", sa.String(length=64), nullable=True),
        sa.Column("item_key", sa.String(length=1000), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["queue_jobs.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["business_index_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "campaign_id",
        "segment_id",
        "job_id",
        "stage",
        "event_type",
        "status",
        "provider_id",
        "business_id",
        "lead_id",
    ):
        op.create_index(
            op.f(f"ix_run_pipeline_events_{column}"),
            "run_pipeline_events",
            [column],
        )
    op.create_index(
        "ix_run_pipeline_events_campaign_created",
        "run_pipeline_events",
        ["campaign_id", "created_at"],
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("run_pipeline_events"):
        op.drop_table("run_pipeline_events")
