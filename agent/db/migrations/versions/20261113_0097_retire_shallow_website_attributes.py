"""remove retired shallow website opportunity attributes

Revision ID: 20261113_0097
Revises: 20261113_0096
Create Date: 2026-11-13

These page-element checks were retired from lead matching because shallow
crawls cannot reliably prove that a form or CTA is absent. Keeping their old
rows made exports and administration noisy and invited accidental reuse.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261113_0097"
down_revision = "20261113_0096"
branch_labels = None
depends_on = None


RETIRED_KEYS = (
    "uses_https",
    "mobile_viewport_present",
    "quote_or_booking_form_present",
    "contact_form_present",
    "primary_cta_present",
    "click_to_call_present",
    "no_quote_flow",
    "no_contact_form",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "business_attributes" in tables:
        attributes = sa.Table(
            "business_attributes", sa.MetaData(), autoload_with=bind
        )
        bind.execute(
            attributes.delete().where(attributes.c.attribute_key.in_(RETIRED_KEYS))
        )

    if "signal_definitions" in tables:
        definitions = sa.Table(
            "signal_definitions", sa.MetaData(), autoload_with=bind
        )
        bind.execute(
            definitions.update()
            .where(definitions.c.key.in_(RETIRED_KEYS))
            .values(status="retired")
        )


def downgrade() -> None:
    # Removed observations cannot be reconstructed safely. Collectors may be
    # re-enabled explicitly if these diagnostics are needed in the future.
    pass

