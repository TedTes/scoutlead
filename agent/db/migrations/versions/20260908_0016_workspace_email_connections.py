"""scope email connections to workspaces

Revision ID: 20260908_0016
Revises: 20260904_0015
Create Date: 2026-09-08
"""

from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "20260908_0016"
down_revision = "20260904_0015"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "workspace_default"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if not inspector.has_table("email_connections"):
        return

    if inspector.has_table("workspaces"):
        now = datetime.utcnow()
        bind.execute(
            sa.text(
                """
                INSERT INTO workspaces (id, name, clerk_organization_id, created_at, updated_at)
                SELECT :id, :name, NULL, :now, :now
                WHERE NOT EXISTS (SELECT 1 FROM workspaces WHERE id = :id)
                """
            ),
            {"id": DEFAULT_WORKSPACE_ID, "name": "Default workspace", "now": now},
        )

    columns = {column["name"] for column in inspector.get_columns("email_connections")}
    if "workspace_id" not in columns:
        op.add_column("email_connections", sa.Column("workspace_id", sa.String(length=255), nullable=True))

    if inspector.has_table("products"):
        bind.execute(
            sa.text(
                """
                UPDATE email_connections
                SET workspace_id = COALESCE(
                    (
                        SELECT products.workspace_id
                        FROM products
                        WHERE products.id = email_connections.product_id
                    ),
                    :workspace_id
                )
                WHERE workspace_id IS NULL
                """
            ),
            {"workspace_id": DEFAULT_WORKSPACE_ID},
        )
    else:
        bind.execute(
            sa.text(
                """
                UPDATE email_connections
                SET workspace_id = :workspace_id
                WHERE workspace_id IS NULL
                """
            ),
            {"workspace_id": DEFAULT_WORKSPACE_ID},
        )

    bind.execute(
        sa.text(
            """
            DELETE FROM email_connections
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT
                        id,
                        ROW_NUMBER() OVER (
                            PARTITION BY workspace_id, provider
                            ORDER BY
                                CASE WHEN disconnected_at IS NULL THEN 0 ELSE 1 END,
                                updated_at DESC,
                                connected_at DESC,
                                created_at DESC,
                                id DESC
                        ) AS duplicate_rank
                    FROM email_connections
                    WHERE workspace_id IS NOT NULL
                ) ranked_connections
                WHERE duplicate_rank > 1
            )
            """
        )
    )

    indexes = {index["name"] for index in inspector.get_indexes("email_connections")}
    if "ix_email_connections_workspace_id" not in indexes:
        op.create_index(
            op.f("ix_email_connections_workspace_id"),
            "email_connections",
            ["workspace_id"],
            unique=False,
        )

    uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("email_connections")}
    if dialect == "postgresql":
        if "uq_email_connections_product_provider" in uniques:
            op.drop_constraint(
                "uq_email_connections_product_provider",
                "email_connections",
                type_="unique",
            )
        op.alter_column(
            "email_connections",
            "product_id",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        op.alter_column(
            "email_connections",
            "workspace_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
        if inspector.has_table("workspaces"):
            foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("email_connections")}
            if "fk_email_connections_workspace_id_workspaces" not in foreign_keys:
                op.create_foreign_key(
                    "fk_email_connections_workspace_id_workspaces",
                    "email_connections",
                    "workspaces",
                    ["workspace_id"],
                    ["id"],
                )
        uniques = {constraint["name"] for constraint in sa.inspect(bind).get_unique_constraints("email_connections")}
        if "uq_email_connections_workspace_provider" not in uniques:
            op.create_unique_constraint(
                "uq_email_connections_workspace_provider",
                "email_connections",
                ["workspace_id", "provider"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("email_connections"):
        return

    dialect = bind.dialect.name
    indexes = {index["name"] for index in inspector.get_indexes("email_connections")}
    uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("email_connections")}
    columns = {column["name"] for column in inspector.get_columns("email_connections")}

    if dialect == "postgresql":
        foreign_keys = {foreign_key["name"] for foreign_key in inspector.get_foreign_keys("email_connections")}
        if "fk_email_connections_workspace_id_workspaces" in foreign_keys:
            op.drop_constraint(
                "fk_email_connections_workspace_id_workspaces",
                "email_connections",
                type_="foreignkey",
            )
        if "uq_email_connections_workspace_provider" in uniques:
            op.drop_constraint(
                "uq_email_connections_workspace_provider",
                "email_connections",
                type_="unique",
            )
        bind.execute(sa.text("DELETE FROM email_connections WHERE product_id IS NULL"))
        op.alter_column(
            "email_connections",
            "product_id",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        if "uq_email_connections_product_provider" not in uniques:
            op.create_unique_constraint(
                "uq_email_connections_product_provider",
                "email_connections",
                ["product_id", "provider"],
            )

    if "ix_email_connections_workspace_id" in indexes:
        op.drop_index(op.f("ix_email_connections_workspace_id"), table_name="email_connections")
    if "workspace_id" in columns:
        op.drop_column("email_connections", "workspace_id")
