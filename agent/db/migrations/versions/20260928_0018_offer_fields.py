"""reframe products as offers

Revision ID: 20260928_0018
Revises: 20260915_0017
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260928_0018"
down_revision = "20260915_0017"
branch_labels = None
depends_on = None


OPTIONAL_TEXT_COLUMNS = (
    "product_description",
    "problem_being_solved",
    "value_proposition",
    "validation_goal",
    "outreach_objective",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("products"):
        return

    columns = {column["name"] for column in inspector.get_columns("products")}
    if "offer_summary" not in columns:
        op.add_column("products", sa.Column("offer_summary", sa.Text(), nullable=True))
    if "ideal_customer_signals" not in columns:
        op.add_column(
            "products",
            sa.Column("ideal_customer_signals", sa.JSON(), nullable=False, server_default="[]"),
        )
    if "exclusions" not in columns:
        op.add_column(
            "products",
            sa.Column("exclusions", sa.JSON(), nullable=False, server_default="[]"),
        )
    if "typical_deal_value" not in columns:
        op.add_column("products", sa.Column("typical_deal_value", sa.Text(), nullable=True))

    for column_name in OPTIONAL_TEXT_COLUMNS:
        if column_name in columns:
            op.alter_column(
                "products",
                column_name,
                existing_type=sa.Text(),
                nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("products"):
        return

    columns = {column["name"] for column in inspector.get_columns("products")}
    if "product_description" in columns:
        bind.execute(
            sa.text(
                "UPDATE products SET product_description = "
                "COALESCE(product_description, offer_summary, product_name)"
            )
        )
    fallback_values = {
        "problem_being_solved": "Not specified.",
        "value_proposition": "Not specified.",
        "validation_goal": "Book customer discovery interviews.",
        "outreach_objective": "Start a relevant sales conversation.",
    }
    for column_name, fallback in fallback_values.items():
        if column_name in columns:
            bind.execute(
                sa.text(
                    f"UPDATE products SET {column_name} = :fallback "
                    f"WHERE {column_name} IS NULL"
                ),
                {"fallback": fallback},
            )
    for column_name in OPTIONAL_TEXT_COLUMNS:
        if column_name in columns:
            op.alter_column(
                "products",
                column_name,
                existing_type=sa.Text(),
                nullable=False,
            )

    for column_name in (
        "typical_deal_value",
        "exclusions",
        "ideal_customer_signals",
        "offer_summary",
    ):
        if column_name in columns:
            op.drop_column("products", column_name)
