"""add user workspaces

Revision ID: 20260904_0015
Revises: 20260903_0014
Create Date: 2026-09-04
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260904_0015"
down_revision = "20260903_0014"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "workspace_default"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("clerk_user_id", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("clerk_user_id", name="uq_users_clerk_user_id"),
        )
        op.create_index(op.f("ix_users_clerk_user_id"), "users", ["clerk_user_id"], unique=True)

    if not inspector.has_table("workspaces"):
        op.create_table(
            "workspaces",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("clerk_organization_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("clerk_organization_id", name="uq_workspaces_clerk_organization_id"),
        )
        op.create_index(
            op.f("ix_workspaces_clerk_organization_id"),
            "workspaces",
            ["clerk_organization_id"],
            unique=True,
        )

    if not inspector.has_table("workspace_members"):
        op.create_table(
            "workspace_members",
            sa.Column("id", sa.String(length=255), nullable=False),
            sa.Column("workspace_id", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id",
                "user_id",
                name="uq_workspace_members_workspace_user",
            ),
        )
        op.create_index(
            op.f("ix_workspace_members_workspace_id"),
            "workspace_members",
            ["workspace_id"],
            unique=False,
        )
        op.create_index(
            op.f("ix_workspace_members_user_id"),
            "workspace_members",
            ["user_id"],
            unique=False,
        )

    now = datetime.utcnow()
    bind.execute(
        sa.text(
            """
            INSERT INTO workspaces (id, name, clerk_organization_id, created_at, updated_at)
            SELECT :id, :name, NULL, :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM workspaces WHERE id = :id)
            """
        ).bindparams(
            sa.bindparam("id", type_=sa.String(length=255)),
            sa.bindparam("name", type_=sa.String(length=255)),
            sa.bindparam("now", type_=sa.DateTime(timezone=True)),
        ),
        {"id": DEFAULT_WORKSPACE_ID, "name": "Default workspace", "now": now},
    )

    if inspector.has_table("products"):
        product_columns = {column["name"] for column in inspector.get_columns("products")}
        if "workspace_id" not in product_columns:
            op.add_column("products", sa.Column("workspace_id", sa.String(length=255), nullable=True))

        bind.execute(
            sa.text("UPDATE products SET workspace_id = :workspace_id WHERE workspace_id IS NULL"),
            {"workspace_id": DEFAULT_WORKSPACE_ID},
        )

        existing_indexes = {index["name"] for index in inspector.get_indexes("products")}
        if "ix_products_workspace_id" not in existing_indexes:
            op.create_index(op.f("ix_products_workspace_id"), "products", ["workspace_id"], unique=False)

        existing_indexes = {index["name"] for index in inspector.get_indexes("products")}
        existing_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("products")
        }
        if "ix_products_source_fingerprint" in existing_indexes:
            op.drop_index("ix_products_source_fingerprint", table_name="products")
        op.create_index(
            "ix_products_source_fingerprint",
            "products",
            ["source_fingerprint"],
            unique=False,
        )
        if (
            "uq_products_workspace_source_fingerprint" not in existing_uniques
            and "ix_products_workspace_source_fingerprint_unique" not in existing_indexes
        ):
            op.create_index(
                "ix_products_workspace_source_fingerprint_unique",
                "products",
                ["workspace_id", "source_fingerprint"],
                unique=True,
            )

        if dialect != "sqlite":
            existing_fks = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("products")}
            if "fk_products_workspace_id_workspaces" not in existing_fks:
                op.create_foreign_key(
                    "fk_products_workspace_id_workspaces",
                    "products",
                    "workspaces",
                    ["workspace_id"],
                    ["id"],
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if inspector.has_table("products"):
        product_columns = {column["name"] for column in inspector.get_columns("products")}
        existing_indexes = {index["name"] for index in inspector.get_indexes("products")}
        if dialect != "sqlite":
            existing_fks = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("products")}
            if "fk_products_workspace_id_workspaces" in existing_fks:
                op.drop_constraint("fk_products_workspace_id_workspaces", "products", type_="foreignkey")
        if "ix_products_workspace_id" in existing_indexes:
            op.drop_index(op.f("ix_products_workspace_id"), table_name="products")
        if "ix_products_workspace_source_fingerprint_unique" in existing_indexes:
            op.drop_index("ix_products_workspace_source_fingerprint_unique", table_name="products")
        if "workspace_id" in product_columns:
            op.drop_column("products", "workspace_id")

    if inspector.has_table("workspace_members"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("workspace_members")}
        if "ix_workspace_members_user_id" in existing_indexes:
            op.drop_index(op.f("ix_workspace_members_user_id"), table_name="workspace_members")
        if "ix_workspace_members_workspace_id" in existing_indexes:
            op.drop_index(op.f("ix_workspace_members_workspace_id"), table_name="workspace_members")
        op.drop_table("workspace_members")

    if inspector.has_table("workspaces"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("workspaces")}
        if "ix_workspaces_clerk_organization_id" in existing_indexes:
            op.drop_index(op.f("ix_workspaces_clerk_organization_id"), table_name="workspaces")
        op.drop_table("workspaces")

    if inspector.has_table("users"):
        existing_indexes = {index["name"] for index in inspector.get_indexes("users")}
        if "ix_users_clerk_user_id" in existing_indexes:
            op.drop_index(op.f("ix_users_clerk_user_id"), table_name="users")
        op.drop_table("users")
