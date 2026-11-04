"""add concept artifacts for personalized outreach

Revision ID: 20261104_0078
Revises: 20261104_0077
Create Date: 2026-11-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261104_0078"
down_revision = "20261104_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("lead_concepts"):
        return
    op.create_table(
        "lead_concepts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=False),
        sa.Column("source_result_id", sa.String(length=64), nullable=True),
        sa.Column("concept_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("concept_url", sa.Text(), nullable=True),
        sa.Column("personalization_note", sa.Text(), nullable=True),
        sa.Column("feature_highlights", sa.JSON(), nullable=False),
        sa.Column("safeguards", sa.JSON(), nullable=False),
        sa.Column("instagram_message", sa.Text(), nullable=False),
        sa.Column("follow_up_message", sa.Text(), nullable=False),
        sa.Column("call_opener", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("follow_up_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(
            ["source_result_id"],
            ["audience_results.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "business_id",
            name="uq_lead_concepts_workspace_business",
        ),
    )
    op.create_index("ix_lead_concepts_workspace_id", "lead_concepts", ["workspace_id"])
    op.create_index("ix_lead_concepts_business_id", "lead_concepts", ["business_id"])
    op.create_index(
        "ix_lead_concepts_source_result_id", "lead_concepts", ["source_result_id"]
    )
    op.create_index("ix_lead_concepts_status", "lead_concepts", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("lead_concepts"):
        op.drop_table("lead_concepts")
