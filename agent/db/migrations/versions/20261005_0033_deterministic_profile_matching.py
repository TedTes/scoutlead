"""add deterministic profile matching fields and delivery items

Revision ID: 20261005_0033
Revises: 20261004_0032
Create Date: 2026-10-05
"""

from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from canonical.attributes import extract_business_attributes
from territories.markets import market_center


revision = "20261005_0033"
down_revision = "20261004_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("businesses"):
        return

    columns = {column["name"] for column in inspector.get_columns("businesses")}
    additions = [
        ("latitude", sa.Column("latitude", sa.Float(), nullable=True)),
        ("longitude", sa.Column("longitude", sa.Float(), nullable=True)),
        (
            "customer_kind",
            sa.Column(
                "customer_kind",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            ),
        ),
        ("is_chain", sa.Column("is_chain", sa.Boolean(), nullable=True)),
        ("is_franchise", sa.Column("is_franchise", sa.Boolean(), nullable=True)),
        ("is_directory", sa.Column("is_directory", sa.Boolean(), nullable=True)),
        ("is_agency", sa.Column("is_agency", sa.Boolean(), nullable=True)),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column("businesses", column)

    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("businesses")}
    for name, fields in (
        ("ix_businesses_customer_kind", ["customer_kind"]),
        ("ix_businesses_is_chain", ["is_chain"]),
        ("ix_businesses_is_franchise", ["is_franchise"]),
        ("ix_businesses_is_directory", ["is_directory"]),
        ("ix_businesses_is_agency", ["is_agency"]),
        ("ix_businesses_location", ["latitude", "longitude"]),
    ):
        if name not in indexes:
            op.create_index(name, "businesses", fields)

    if not inspector.has_table("profile_delivery_items"):
        op.create_table(
            "profile_delivery_items",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column(
                "profile_id",
                sa.String(length=64),
                sa.ForeignKey("territories.id"),
                nullable=False,
            ),
            sa.Column(
                "delivery_id",
                sa.String(length=64),
                sa.ForeignKey("territory_deliveries.id"),
                nullable=False,
            ),
            sa.Column(
                "business_id",
                sa.String(length=64),
                sa.ForeignKey("businesses.id"),
                nullable=False,
            ),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "profile_id",
                "business_id",
                name="uq_profile_delivery_items_profile_business",
            ),
            sa.UniqueConstraint(
                "delivery_id",
                "business_id",
                name="uq_profile_delivery_items_delivery_business",
            ),
        )
        op.create_index(
            "ix_profile_delivery_items_profile_id",
            "profile_delivery_items",
            ["profile_id"],
        )
        op.create_index(
            "ix_profile_delivery_items_delivery_id",
            "profile_delivery_items",
            ["delivery_id"],
        )
        op.create_index(
            "ix_profile_delivery_items_business_id",
            "profile_delivery_items",
            ["business_id"],
        )

    _backfill_business_attributes(bind)
    _backfill_profile_centers(bind)
    _backfill_delivery_items(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("profile_delivery_items"):
        op.drop_table("profile_delivery_items")
    if not inspector.has_table("businesses"):
        return
    indexes = {index["name"] for index in inspector.get_indexes("businesses")}
    for name in (
        "ix_businesses_location",
        "ix_businesses_is_agency",
        "ix_businesses_is_directory",
        "ix_businesses_is_franchise",
        "ix_businesses_is_chain",
        "ix_businesses_customer_kind",
    ):
        if name in indexes:
            op.drop_index(name, table_name="businesses")
    columns = {column["name"] for column in inspector.get_columns("businesses")}
    for name in (
        "is_agency",
        "is_directory",
        "is_franchise",
        "is_chain",
        "customer_kind",
        "longitude",
        "latitude",
    ):
        if name in columns:
            op.drop_column("businesses", name)


def _backfill_business_attributes(bind) -> None:
    metadata = sa.MetaData()
    businesses = sa.Table("businesses", metadata, autoload_with=bind)
    observations = sa.Table("source_observations", metadata, autoload_with=bind)
    payloads_by_business: dict[str, list[dict]] = {}
    for business_id, payload in bind.execute(
        sa.select(observations.c.business_id, observations.c.raw_payload).order_by(
            observations.c.observed_at.desc()
        )
    ):
        if isinstance(payload, dict):
            payloads_by_business.setdefault(str(business_id), []).append(payload)

    for row in bind.execute(
        sa.select(
            businesses.c.id,
            businesses.c.category_key,
            businesses.c.status,
        )
    ).mappings():
        attributes = extract_business_attributes(
            payloads_by_business.get(str(row["id"]), []),
            category=row["category_key"],
        )
        values = {
            "customer_kind": attributes.customer_kind or "unknown",
            "latitude": attributes.latitude,
            "longitude": attributes.longitude,
            "is_chain": attributes.is_chain,
            "is_franchise": attributes.is_franchise,
            "is_directory": attributes.is_directory,
            "is_agency": attributes.is_agency,
        }
        if attributes.operational is False:
            values["status"] = "closed"
        bind.execute(
            businesses.update().where(businesses.c.id == row["id"]).values(**values)
        )


def _backfill_delivery_items(bind) -> None:
    metadata = sa.MetaData()
    deliveries = sa.Table("territory_deliveries", metadata, autoload_with=bind)
    profiles = sa.Table("territories", metadata, autoload_with=bind)
    leads = sa.Table("leads", metadata, autoload_with=bind)
    items = sa.Table("profile_delivery_items", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(
            deliveries.c.territory_id,
            deliveries.c.id.label("delivery_id"),
            leads.c.business_id,
            leads.c.qualification,
            profiles.c.min_fit,
            sa.func.coalesce(
                deliveries.c.delivered_at,
                deliveries.c.created_at,
            ).label("delivered_at"),
        )
        .join(leads, leads.c.campaign_id == deliveries.c.campaign_id)
        .join(profiles, profiles.c.id == deliveries.c.territory_id)
        .where(leads.c.business_id.is_not(None))
        .where(deliveries.c.status.in_(["ready", "partial"]))
        .order_by(deliveries.c.created_at)
    ).mappings()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        qualification = row["qualification"]
        fit_status = (
            qualification.get("fit_status")
            if isinstance(qualification, dict)
            else None
        )
        allowed_fit = {"good_fit"}
        if row["min_fit"] == "maybe":
            allowed_fit.add("maybe")
        if fit_status not in allowed_fit:
            continue
        key = (str(row["territory_id"]), str(row["business_id"]))
        if key in seen:
            continue
        seen.add(key)
        delivered_at = row["delivered_at"]
        bind.execute(
            items.insert().values(
                id=f"profile_delivery_item_{uuid4().hex}",
                profile_id=row["territory_id"],
                delivery_id=row["delivery_id"],
                business_id=row["business_id"],
                delivered_at=delivered_at,
                created_at=delivered_at,
                updated_at=delivered_at,
            )
        )


def _backfill_profile_centers(bind) -> None:
    metadata = sa.MetaData()
    territories = sa.Table("territories", metadata, autoload_with=bind)
    for row in bind.execute(
        sa.select(
            territories.c.id,
            territories.c.city,
            territories.c.latitude,
            territories.c.longitude,
        )
    ).mappings():
        if row["latitude"] is not None and row["longitude"] is not None:
            continue
        center = market_center(str(row["city"] or ""))
        if center is None:
            continue
        bind.execute(
            territories.update()
            .where(territories.c.id == row["id"])
            .values(latitude=center[0], longitude=center[1])
        )
