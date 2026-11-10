"""add workspace-specific niche preferences

Revision ID: 20261110_0082
Revises: 20261110_0081
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20261110_0082"
down_revision = "20261110_0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("niches")}
    if "display_order" not in columns:
        op.add_column(
            "niches",
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        )
    if "catalog_status" not in columns:
        op.add_column(
            "niches",
            sa.Column(
                "catalog_status",
                sa.String(length=32),
                nullable=False,
                server_default="supported",
            ),
        )
        op.create_index("ix_niches_catalog_status", "niches", ["catalog_status"])
    if "created_by_workspace_id" not in columns:
        op.add_column(
            "niches",
            sa.Column("created_by_workspace_id", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_niches_created_by_workspace_id",
            "niches",
            ["created_by_workspace_id"],
        )
    if not sa.inspect(bind).has_table("workspace_niche_preferences"):
        op.create_table(
            "workspace_niche_preferences",
            sa.Column("workspace_id", sa.String(length=255), nullable=False),
            sa.Column("niche_id", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["niche_id"], ["niches.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("workspace_id", "niche_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("workspace_niche_preferences"):
        op.drop_table("workspace_niche_preferences")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("niches")}
    if "catalog_status" in columns:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("niches")}
        if "ix_niches_catalog_status" in indexes:
            op.drop_index("ix_niches_catalog_status", table_name="niches")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("niches") as batch_op:
                batch_op.drop_column("catalog_status")
        else:
            op.drop_column("niches", "catalog_status")
        columns.remove("catalog_status")
    if "created_by_workspace_id" in columns:
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes("niches")}
        if "ix_niches_created_by_workspace_id" in indexes:
            op.drop_index("ix_niches_created_by_workspace_id", table_name="niches")
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("niches") as batch_op:
                batch_op.drop_column("created_by_workspace_id")
        else:
            op.drop_column("niches", "created_by_workspace_id")
        columns.remove("created_by_workspace_id")
    if "display_order" in columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("niches") as batch_op:
                batch_op.drop_column("display_order")
        else:
            op.drop_column("niches", "display_order")
