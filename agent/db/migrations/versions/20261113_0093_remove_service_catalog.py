"""remove redundant service catalog tables

Revision ID: 20261113_0093
Revises: 20261113_0092
Create Date: 2026-11-13

Saved-search opportunity choices now map directly to canonical business
attribute keys in application code.  The service catalog and join table no
longer participate in collection or matching.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261113_0093"
down_revision = "20261113_0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "service_signal_mappings" in tables:
        op.drop_table("service_signal_mappings")
    if "service_definitions" in tables:
        op.drop_table("service_definitions")


def downgrade() -> None:
    raise RuntimeError(
        "20261113_0093 is intentionally irreversible: saved-search criteria "
        "now map directly to business attributes."
    )
