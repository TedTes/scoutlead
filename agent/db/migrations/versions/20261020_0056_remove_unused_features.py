"""detach unused quality, insights, demo, draft-cache, and summary features

Revision ID: 20261020_0056
Revises: 20261019_0055
Create Date: 2026-10-20
"""


revision = "20261020_0056"
down_revision = "20261019_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the retired tables for one compatibility deployment. This migration
    # runs before Railway replaces the API and worker, so the previous runtime
    # can still hold locks on these tables and make DROP TABLE time out.
    # A follow-up migration may drop them after this runtime has been deployed.
    pass


def downgrade() -> None:
    # This revision changes only application/runtime compatibility state.
    pass
