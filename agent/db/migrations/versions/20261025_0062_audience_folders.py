"""add optional user-managed audience folders

Revision ID: 20261025_0062
Revises: 20261023_0061
Create Date: 2026-10-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20261025_0062"
down_revision = "20261023_0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("audience_folders"):
        op.create_table(
            "audience_folders",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("workspace_id", sa.String(length=255), nullable=False),
            sa.Column("product_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "workspace_id",
                "product_id",
                "name",
                name="uq_audience_folders_workspace_product_name",
            ),
        )
        op.create_index(
            "ix_audience_folders_workspace_id",
            "audience_folders",
            ["workspace_id"],
        )
        op.create_index(
            "ix_audience_folders_product_id",
            "audience_folders",
            ["product_id"],
        )

    inspector = sa.inspect(bind)
    territory_columns = {column["name"] for column in inspector.get_columns("territories")}
    if "folder_id" not in territory_columns:
        column = sa.Column("folder_id", sa.String(length=64), nullable=True)
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("territories") as batch_op:
                batch_op.add_column(column)
                batch_op.create_foreign_key(
                    "fk_territories_folder_id_audience_folders",
                    "audience_folders",
                    ["folder_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        else:
            op.add_column("territories", column)
            op.create_foreign_key(
                "fk_territories_folder_id_audience_folders",
                "territories",
                "audience_folders",
                ["folder_id"],
                ["id"],
                ondelete="SET NULL",
            )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("territories")}
    if "ix_territories_folder_id" not in indexes:
        op.create_index("ix_territories_folder_id", "territories", ["folder_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("territories"):
        columns = {column["name"] for column in inspector.get_columns("territories")}
        if "folder_id" in columns:
            indexes = {index["name"] for index in inspector.get_indexes("territories")}
            if "ix_territories_folder_id" in indexes:
                op.drop_index("ix_territories_folder_id", table_name="territories")
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("territories") as batch_op:
                    batch_op.drop_column("folder_id")
            else:
                op.drop_column("territories", "folder_id")
    if sa.inspect(bind).has_table("audience_folders"):
        op.drop_table("audience_folders")
