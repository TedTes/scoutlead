"""normalize workflow-only lead statuses

Revision ID: 20261113_0095
Revises: 20261113_0094
Create Date: 2026-11-13

Migration 0089 briefly copied shortlist/contact workflow states into the lead
lifecycle status column. Those values are not members of LeadStatus and cause
API response validation to fail. The workflow timestamps remain authoritative.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261113_0095"
down_revision = "20261113_0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "leads" not in inspector.get_table_names():
        return

    leads = sa.Table("leads", sa.MetaData(), autoload_with=bind)
    if "status" not in leads.c:
        return

    bind.execute(
        leads.update()
        .where(leads.c.status == "contacted")
        .values(status="sent")
    )
    bind.execute(
        leads.update()
        .where(leads.c.status == "shortlisted")
        .values(status="qualified")
    )


def downgrade() -> None:
    # The old values are invalid lifecycle statuses and cannot be restored
    # safely. Workflow state remains available in the timestamp columns.
    pass
