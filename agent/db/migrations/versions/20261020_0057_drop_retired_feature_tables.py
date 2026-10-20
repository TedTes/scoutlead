"""finish the retired-feature compatibility deployment

Revision ID: 20261020_0057
Revises: 20261020_0056
Create Date: 2026-10-20
"""


revision = "20261020_0057"
down_revision = "20261020_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The worker previously held database transactions open across external
    # signal-collection calls. Keep the tables until the transaction-boundary
    # fix in this deployment has replaced that worker process.
    pass


def downgrade() -> None:
    pass
