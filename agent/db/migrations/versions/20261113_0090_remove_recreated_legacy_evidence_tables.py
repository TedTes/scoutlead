"""remove legacy evidence tables left by mixed-version deployments

Revision ID: 20261113_0090
Revises: 20261112_0089
Create Date: 2026-11-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261113_0090"
down_revision = "20261112_0089"
branch_labels = None
depends_on = None


RETIRED_TABLES = (
    "business_fact_changes",
    "fact_claims",
    "validation_results",
    "business_search_evaluations",
    "business_facts",
    "source_observations",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("SET LOCAL lock_timeout = '120s'"))

    tables = set(sa.inspect(bind).get_table_names())
    for table_name in RETIRED_TABLES:
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20261113_0090 is intentionally irreversible: legacy evidence tables were "
        "already consolidated into business_attributes by 20261112_0088."
    )
