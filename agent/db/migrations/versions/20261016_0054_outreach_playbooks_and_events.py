"""add managed outreach playbooks and events

Revision ID: 20261016_0054
Revises: 20261016_0053
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "20261016_0054"
down_revision = "20261016_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("outreach_playbooks"):
        op.create_table(
            "outreach_playbooks",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("service_key", sa.String(length=120), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("definition", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("service_key", name="uq_outreach_playbooks_service_key"),
        )
        op.create_index("ix_outreach_playbooks_service_key", "outreach_playbooks", ["service_key"])
        op.create_index("ix_outreach_playbooks_status", "outreach_playbooks", ["status"])

    if not inspector.has_table("outreach_events"):
        op.create_table(
            "outreach_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("workspace_id", sa.String(length=255), nullable=True),
            sa.Column("package_id", sa.String(length=64), nullable=False),
            sa.Column("channel", sa.String(length=32), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("variant_id", sa.String(length=120), nullable=True),
            sa.Column("event_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["package_id"], ["outreach_packages.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_outreach_events_workspace_id", "outreach_events", ["workspace_id"])
        op.create_index("ix_outreach_events_package_id", "outreach_events", ["package_id"])
        op.create_index("ix_outreach_events_channel", "outreach_events", ["channel"])
        op.create_index("ix_outreach_events_event_type", "outreach_events", ["event_type"])
        op.create_index("ix_outreach_events_variant_id", "outreach_events", ["variant_id"])
        op.create_index("ix_outreach_events_package_created", "outreach_events", ["package_id", "created_at"])
        op.create_index("ix_outreach_events_workspace_event", "outreach_events", ["workspace_id", "event_type"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("outreach_events"):
        op.drop_table("outreach_events")
    if inspector.has_table("outreach_playbooks"):
        op.drop_table("outreach_playbooks")
