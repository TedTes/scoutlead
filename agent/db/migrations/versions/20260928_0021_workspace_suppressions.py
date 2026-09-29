"""scope contact suppressions to workspaces

Revision ID: 20260928_0021
Revises: 20260928_0020
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0021"
down_revision = "20260928_0020"
branch_labels = None
depends_on = None


OLD_UNIQUE = "uq_contact_suppressions_scope_product_kind_value"
NEW_UNIQUE = "uq_contact_suppressions_scope_workspace_product_kind_value"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("contact_suppressions")}
    unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("contact_suppressions")
    }
    with op.batch_alter_table("contact_suppressions") as batch_op:
        if "workspace_id" not in columns:
            batch_op.add_column(sa.Column("workspace_id", sa.String(length=255)))
            batch_op.create_foreign_key(
                "fk_contact_suppressions_workspace_id_workspaces",
                "workspaces",
                ["workspace_id"],
                ["id"],
            )
            batch_op.create_index("ix_contact_suppressions_workspace_id", ["workspace_id"])
        if OLD_UNIQUE in unique_names:
            batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        if NEW_UNIQUE not in unique_names:
            batch_op.create_unique_constraint(
                NEW_UNIQUE,
                ["scope", "workspace_id", "product_id", "kind", "value"],
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("contact_suppressions")}
    unique_names = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("contact_suppressions")
    }
    with op.batch_alter_table("contact_suppressions") as batch_op:
        if NEW_UNIQUE in unique_names:
            batch_op.drop_constraint(NEW_UNIQUE, type_="unique")
        if OLD_UNIQUE not in unique_names:
            batch_op.create_unique_constraint(
                OLD_UNIQUE,
                ["scope", "product_id", "kind", "value"],
            )
        if "workspace_id" in columns:
            batch_op.drop_index("ix_contact_suppressions_workspace_id")
            batch_op.drop_constraint(
                "fk_contact_suppressions_workspace_id_workspaces",
                type_="foreignkey",
            )
            batch_op.drop_column("workspace_id")
