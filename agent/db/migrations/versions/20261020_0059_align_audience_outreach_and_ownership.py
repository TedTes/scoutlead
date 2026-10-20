"""align legacy delivery cleanup, outreach handoff, and personal ownership

Revision ID: 20261020_0059
Revises: 20261020_0058
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20261020_0059"
down_revision = "20261020_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # These tables belonged to the retired delivery runtime. Environments may
    # already have removed either one, so cleanup must be safe to resume.
    op.execute(sa.text('DROP TABLE IF EXISTS "profile_delivery_items"'))
    op.execute(sa.text('DROP TABLE IF EXISTS "territory_deliveries"'))

    workspace_columns = {
        column["name"] for column in inspector.get_columns("workspaces")
    }
    if "owner_user_id" not in workspace_columns:
        op.add_column(
            "workspaces",
            sa.Column("owner_user_id", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_workspaces_owner_user_id",
            "workspaces",
            ["owner_user_id"],
        )
        op.create_foreign_key(
            "fk_workspaces_owner_user_id_users",
            "workspaces",
            "users",
            ["owner_user_id"],
            ["id"],
        )

    if inspector.has_table("workspace_members"):
        op.execute(
            sa.text(
                """
                UPDATE workspaces AS workspace
                SET owner_user_id = membership.user_id
                FROM (
                    SELECT DISTINCT ON (workspace_id) workspace_id, user_id
                    FROM workspace_members
                    ORDER BY workspace_id,
                        CASE WHEN role = 'owner' THEN 0 ELSE 1 END,
                        created_at
                ) AS membership
                WHERE membership.workspace_id = workspace.id
                  AND workspace.owner_user_id IS NULL
                """
            )
        )
        op.execute(sa.text('DROP TABLE IF EXISTS "workspace_members"'))

    message_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("messages")
    }
    if "outreach_package_id" not in message_columns:
        op.add_column(
            "messages",
            sa.Column("outreach_package_id", sa.String(length=64), nullable=True),
        )
        op.create_index(
            "ix_messages_outreach_package_id",
            "messages",
            ["outreach_package_id"],
            unique=True,
        )
        op.create_foreign_key(
            "fk_messages_outreach_package_id_outreach_packages",
            "messages",
            "outreach_packages",
            ["outreach_package_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    raise RuntimeError(
        "This migration removes retired delivery and team-membership data and cannot be reversed safely"
    )
