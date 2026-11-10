"""map audience folders to niches

Revision ID: 20261110_0081
Revises: 20261107_0080
Create Date: 2026-11-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20261110_0081"
down_revision = "20261107_0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audience_folders")}
    if "niche_id" not in columns:
        column = sa.Column("niche_id", sa.String(length=64), nullable=True)
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("audience_folders") as batch_op:
                batch_op.add_column(column)
                batch_op.create_foreign_key(
                    "fk_audience_folders_niche_id_niches",
                    "niches",
                    ["niche_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        else:
            op.add_column("audience_folders", column)
            op.create_foreign_key(
                "fk_audience_folders_niche_id_niches",
                "audience_folders",
                "niches",
                ["niche_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Bind one existing single-trade folder per workspace/product/niche. Other
    # user-managed folders remain unbound and continue to work as before.
    candidates = bind.execute(
        sa.text(
            """
            SELECT af.id, af.workspace_id, af.product_id, MIN(t.niche_id) AS niche_id
            FROM audience_folders AS af
            JOIN territories AS t ON t.folder_id = af.id
            WHERE t.niche_id IS NOT NULL
            GROUP BY af.id, af.workspace_id, af.product_id, af.sort_order, af.created_at
            HAVING COUNT(DISTINCT t.niche_id) = 1
            ORDER BY af.sort_order ASC, af.created_at ASC
            """
        )
    ).mappings()
    claimed: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        key = (
            candidate["workspace_id"],
            candidate["product_id"],
            candidate["niche_id"],
        )
        if key in claimed:
            continue
        claimed.add(key)
        bind.execute(
            sa.text(
                "UPDATE audience_folders SET niche_id = :niche_id WHERE id = :folder_id"
            ),
            {"niche_id": candidate["niche_id"], "folder_id": candidate["id"]},
        )

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("audience_folders")}
    if "ix_audience_folders_niche_id" not in indexes:
        op.create_index(
            "ix_audience_folders_niche_id",
            "audience_folders",
            ["niche_id"],
        )

    constraints = {
        constraint["name"]
        for constraint in sa.inspect(bind).get_unique_constraints("audience_folders")
    }
    name = "uq_audience_folders_workspace_product_niche"
    if name not in constraints:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("audience_folders") as batch_op:
                batch_op.create_unique_constraint(
                    name,
                    ["workspace_id", "product_id", "niche_id"],
                )
        else:
            op.create_unique_constraint(
                name,
                "audience_folders",
                ["workspace_id", "product_id", "niche_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("audience_folders"):
        return
    columns = {column["name"] for column in inspector.get_columns("audience_folders")}
    if "niche_id" not in columns:
        return
    indexes = {index["name"] for index in inspector.get_indexes("audience_folders")}
    if "ix_audience_folders_niche_id" in indexes:
        op.drop_index("ix_audience_folders_niche_id", table_name="audience_folders")
    constraint_name = "uq_audience_folders_workspace_product_niche"
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("audience_folders") as batch_op:
            batch_op.drop_constraint(constraint_name, type_="unique")
            batch_op.drop_column("niche_id")
    else:
        op.drop_constraint(
            constraint_name,
            "audience_folders",
            type_="unique",
        )
        op.drop_constraint(
            "fk_audience_folders_niche_id_niches",
            "audience_folders",
            type_="foreignkey",
        )
        op.drop_column("audience_folders", "niche_id")
