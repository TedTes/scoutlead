"""add multi-city saved-search locations

Revision ID: 20261111_0084
Revises: 20261110_0083
Create Date: 2026-11-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20261111_0084"
down_revision = "20261110_0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    territory_columns = {column["name"] for column in inspector.get_columns("territories")}
    if "locations" not in territory_columns:
        op.add_column(
            "territories",
            sa.Column("locations", sa.JSON(), nullable=False, server_default="[]"),
        )
    constraints = {
        constraint.get("name")
        for constraint in inspector.get_unique_constraints("coverage_requests")
    }
    if "uq_coverage_requests_run_niche" in constraints:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("coverage_requests") as batch_op:
                batch_op.drop_constraint("uq_coverage_requests_run_niche", type_="unique")
                batch_op.create_unique_constraint(
                    "uq_coverage_requests_run_niche_market",
                    ["run_id", "niche_id", "market_key"],
                )
        else:
            op.drop_constraint("uq_coverage_requests_run_niche", "coverage_requests", type_="unique")
            op.create_unique_constraint(
                "uq_coverage_requests_run_niche_market",
                "coverage_requests",
                ["run_id", "niche_id", "market_key"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("coverage_requests") as batch_op:
            batch_op.drop_constraint("uq_coverage_requests_run_niche_market", type_="unique")
            batch_op.create_unique_constraint(
                "uq_coverage_requests_run_niche", ["run_id", "niche_id"]
            )
        with op.batch_alter_table("territories") as batch_op:
            batch_op.drop_column("locations")
    else:
        op.drop_constraint(
            "uq_coverage_requests_run_niche_market", "coverage_requests", type_="unique"
        )
        op.create_unique_constraint(
            "uq_coverage_requests_run_niche",
            "coverage_requests",
            ["run_id", "niche_id"],
        )
        op.drop_column("territories", "locations")
