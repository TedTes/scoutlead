"""retire the legacy territory delivery pipeline

Revision ID: 20261013_0046
Revises: 20261013_0045
Create Date: 2026-10-13
"""

revision = "20261013_0046"
down_revision = "20261013_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Runtime references are removed in this release. Physical table cleanup is
    # intentionally deferred until the old API and worker processes are gone;
    # otherwise PostgreSQL can wait indefinitely for their table locks.
    pass


def downgrade() -> None:
    pass
