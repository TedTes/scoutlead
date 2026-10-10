"""add admin data stewardship audit events

Revision ID: 20261010_0040
Revises: 20261008_0039
Create Date: 2026-10-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20261010_0040"
down_revision = "20261008_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("actor_email", sa.String(length=320), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_events_actor_id", "admin_audit_events", ["actor_id"])
    op.create_index("ix_admin_audit_events_actor_email", "admin_audit_events", ["actor_email"])
    op.create_index("ix_admin_audit_events_action", "admin_audit_events", ["action"])
    op.create_index("ix_admin_audit_events_entity_type", "admin_audit_events", ["entity_type"])
    op.create_index("ix_admin_audit_events_entity_id", "admin_audit_events", ["entity_id"])
    op.create_index(
        "ix_admin_audit_events_entity_created",
        "admin_audit_events",
        ["entity_type", "entity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("admin_audit_events")
