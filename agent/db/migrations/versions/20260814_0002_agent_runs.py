"""add agent run observability tables

Revision ID: 20260814_0002
Revises: 20260812_0001
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20260814_0002"
down_revision = "20260812_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if not inspector.has_table("agent_runs"):
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("campaign_id", sa.String(length=64), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=64), nullable=False),
            sa.Column("objective", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("current_phase", sa.String(length=64), nullable=True),
            sa.Column("context_snapshot", sa.JSON(), nullable=False),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("max_tool_calls", sa.Integer(), nullable=False),
            sa.Column("max_llm_calls", sa.Integer(), nullable=False),
            sa.Column("max_leads", sa.Integer(), nullable=False),
            sa.Column("tool_call_count", sa.Integer(), nullable=False),
            sa.Column("llm_call_count", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_runs_campaign_id", "agent_runs", ["campaign_id"])
        op.create_index("ix_agent_runs_product_id", "agent_runs", ["product_id"])
        op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    if not inspector.has_table("agent_steps"):
        op.create_table(
            "agent_steps",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("campaign_id", sa.String(length=64), nullable=False),
            sa.Column("phase", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("objective", sa.Text(), nullable=False),
            sa.Column("input_snapshot", sa.JSON(), nullable=False),
            sa.Column("output_snapshot", sa.JSON(), nullable=True),
            sa.Column("observation", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_steps_campaign_id", "agent_steps", ["campaign_id"])
        op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
        op.create_index("ix_agent_steps_status", "agent_steps", ["status"])

    if not inspector.has_table("tool_calls"):
        op.create_table(
            "tool_calls",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("step_id", sa.String(length=64), nullable=True),
            sa.Column("campaign_id", sa.String(length=64), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("args", sa.JSON(), nullable=False),
            sa.Column("observation", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["campaign_id"], ["campaigns.id"]),
            sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
            sa.ForeignKeyConstraint(["step_id"], ["agent_steps.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_tool_calls_campaign_id", "tool_calls", ["campaign_id"])
        op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])
        op.create_index("ix_tool_calls_step_id", "tool_calls", ["step_id"])
        op.create_index("ix_tool_calls_status", "tool_calls", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tool_calls_status", table_name="tool_calls")
    op.drop_index("ix_tool_calls_step_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_run_id", table_name="tool_calls")
    op.drop_index("ix_tool_calls_campaign_id", table_name="tool_calls")
    op.drop_table("tool_calls")

    op.drop_index("ix_agent_steps_status", table_name="agent_steps")
    op.drop_index("ix_agent_steps_run_id", table_name="agent_steps")
    op.drop_index("ix_agent_steps_campaign_id", table_name="agent_steps")
    op.drop_table("agent_steps")

    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index("ix_agent_runs_product_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_campaign_id", table_name="agent_runs")
    op.drop_table("agent_runs")
