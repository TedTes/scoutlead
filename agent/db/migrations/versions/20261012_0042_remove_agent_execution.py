"""remove legacy agent execution tables

Revision ID: 20261012_0042
Revises: 20261012_0041
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_0042"
down_revision = "20261012_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")


def downgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("current_phase", sa.String(64)),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False),
        sa.Column("max_llm_calls", sa.Integer(), nullable=False),
        sa.Column("max_leads", sa.Integer(), nullable=False),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_runs_campaign_id", "agent_runs", ["campaign_id"])
    op.create_index("ix_agent_runs_product_id", "agent_runs", ["product_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("output_snapshot", sa.JSON()),
        sa.Column("observation", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_steps_campaign_id", "agent_steps", ["campaign_id"])
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
    op.create_index("ix_agent_steps_status", "agent_steps", ["status"])

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("step_id", sa.String(64), sa.ForeignKey("agent_steps.id")),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("args", sa.JSON(), nullable=False),
        sa.Column("observation", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_calls_campaign_id", "tool_calls", ["campaign_id"])
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])
    op.create_index("ix_tool_calls_status", "tool_calls", ["status"])
    op.create_index("ix_tool_calls_step_id", "tool_calls", ["step_id"])
