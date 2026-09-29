"""add outcome learning snapshots and lead rank fields

Revision ID: 20260928_0024
Revises: 20260928_0023
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0024"
down_revision = "20260928_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(
            sa.Column("outcome_adjustment", sa.Float(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("rank_score", sa.Float()))
        batch_op.create_index("ix_leads_rank_score", ["rank_score"])
    op.create_table(
        "outcome_models",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("niche_id", sa.String(length=64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("n_contacted", sa.Integer(), nullable=False),
        sa.Column("n_positive", sa.Integer(), nullable=False),
        sa.Column("weights", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "product_id",
            "niche_id",
            name="uq_outcome_models_workspace_product_niche",
        ),
    )
    for column in ("workspace_id", "product_id", "niche_id"):
        op.create_index(f"ix_outcome_models_{column}", "outcome_models", [column])


def downgrade() -> None:
    op.drop_table("outcome_models")
    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_rank_score")
        batch_op.drop_column("rank_score")
        batch_op.drop_column("outcome_adjustment")
