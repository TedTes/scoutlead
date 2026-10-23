"""make audiences niche-driven and preserve canonical places

Revision ID: 20261023_0061
Revises: 20261021_0060
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20261023_0061"
down_revision = "20261021_0060"
branch_labels = None
depends_on = None


NICHE_SEARCH_CONFIG = {
    "home_service_painting": {
        "include_terms": ["paint", "painter", "painting", "decorating"],
        "exclude_terms": ["art gallery", "auto body", "paint store", "supplies"],
    },
    "home_service_hvac": {
        "include_terms": ["hvac", "heating", "cooling", "furnace", "air conditioning"],
        "exclude_terms": ["supply", "supplies", "wholesale", "manufacturer"],
    },
    "home_service_roofing": {
        "include_terms": ["roof", "roofer", "roofing"],
        "exclude_terms": ["supply", "supplies", "truss", "waterproofing store"],
    },
    "home_service_plumbing": {
        "include_terms": ["plumb", "plumber", "plumbing", "drain service"],
        "exclude_terms": ["supply", "supplies", "wholesale", "showroom"],
    },
    "home_service_electrical": {
        "include_terms": ["electric", "electrical", "electrician"],
        "exclude_terms": ["supply", "supplies", "utility", "wholesale"],
    },
    "home_service_cleaning": {
        "include_terms": ["house cleaning", "home cleaning", "residential cleaning", "cleaning service", "maid", "cleaners"],
        "exclude_terms": ["carpet", "duct", "dry clean", "laundry", "janitorial supply"],
    },
    "home_service_landscaping": {
        "include_terms": ["landscape", "landscaping", "landscaper", "lawn care"],
        "exclude_terms": ["architect", "garden centre", "nursery", "supply"],
    },
    "home_service_pest_control": {
        "include_terms": ["pest control", "exterminator", "extermination", "wildlife removal"],
        "exclude_terms": ["supply", "supplies", "product", "manufacturer"],
    },
    "home_service_garage_doors": {
        "include_terms": ["garage door", "overhead door", "garage repair", "door installation"],
        "exclude_terms": ["cabinet", "interior door", "lumber", "supply", "wholesale"],
    },
}


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    niche_columns = _columns("niches")
    if "search_config" not in niche_columns:
        op.add_column(
            "niches",
            sa.Column("search_config", sa.JSON(), nullable=False, server_default="{}"),
        )

    niches = sa.table(
        "niches",
        sa.column("slug", sa.String()),
        sa.column("search_config", sa.JSON()),
    )
    for slug, config in NICHE_SEARCH_CONFIG.items():
        bind.execute(
            niches.update().where(niches.c.slug == slug).values(search_config=config)
        )

    territory_columns = _columns("territories")
    additions = (
        ("place_label", sa.Column("place_label", sa.String(length=500), nullable=True)),
        ("place_provider", sa.Column("place_provider", sa.String(length=64), nullable=True)),
        ("place_external_id", sa.Column("place_external_id", sa.String(length=255), nullable=True)),
        ("country_code", sa.Column("country_code", sa.String(length=2), nullable=True)),
    )
    for name, column in additions:
        if name not in territory_columns:
            op.add_column("territories", column)

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("territories")}
    if "ix_territories_country_code" not in indexes:
        op.create_index("ix_territories_country_code", "territories", ["country_code"])

    bind.execute(
        sa.text(
            "UPDATE territories SET place_label = city "
            "WHERE place_label IS NULL AND city IS NOT NULL AND city <> ''"
        )
    )

    territory_columns = _columns("territories")
    if "trade_keys" in territory_columns:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("territories") as batch_op:
                batch_op.drop_column("trade_keys")
        else:
            op.drop_column("territories", "trade_keys")

    unique_constraints = {
        constraint["name"]
        for constraint in sa.inspect(bind).get_unique_constraints("territories")
        if constraint.get("name")
    }
    constraint_name = "uq_territories_workspace_offer_niche_market_criteria"
    if constraint_name in unique_constraints:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table("territories") as batch_op:
                batch_op.drop_constraint(constraint_name, type_="unique")
        else:
            op.drop_constraint(constraint_name, "territories", type_="unique")


def downgrade() -> None:
    raise RuntimeError(
        "Canonical place identity and retired trade-key data cannot be reconstructed safely"
    )
