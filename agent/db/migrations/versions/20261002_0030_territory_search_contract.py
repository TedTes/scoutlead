"""store scheduled search contracts

Revision ID: 20261002_0030
Revises: 20261002_0029
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0030"
down_revision = "20261002_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("territories")}
    if "search_prompt" not in columns:
        op.add_column("territories", sa.Column("search_prompt", sa.Text(), nullable=True))
    if "search_contract" not in columns:
        op.add_column(
            "territories",
            sa.Column("search_contract", sa.JSON(), nullable=False, server_default="{}"),
        )
    if "evidence_max_age_days" not in columns:
        op.add_column(
            "territories",
            sa.Column("evidence_max_age_days", sa.Integer(), nullable=False, server_default="30"),
        )
    if "criteria_hash" not in columns:
        op.add_column(
            "territories",
            sa.Column("criteria_hash", sa.String(length=64), nullable=False, server_default="default"),
        )
    constraints = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("territories")
    }
    if "uq_territories_workspace_offer_niche_market" in constraints:
        op.drop_constraint(
            "uq_territories_workspace_offer_niche_market",
            "territories",
            type_="unique",
        )
    if "uq_territories_workspace_offer_niche_market_criteria" not in constraints:
        op.create_unique_constraint(
            "uq_territories_workspace_offer_niche_market_criteria",
            "territories",
            ["workspace_id", "product_id", "niche_id", "market_key", "criteria_hash"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_territories_workspace_offer_niche_market_criteria",
        "territories",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_territories_workspace_offer_niche_market",
        "territories",
        ["workspace_id", "product_id", "niche_id", "market_key"],
    )
    op.drop_column("territories", "criteria_hash")
    op.drop_column("territories", "evidence_max_age_days")
    op.drop_column("territories", "search_contract")
    op.drop_column("territories", "search_prompt")
