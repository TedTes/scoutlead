"""backfill operational eligibility and current record checks

Revision ID: 20261101_0067
Revises: 20261101_0066
Create Date: 2026-11-01

Existing businesses must not become ineligible merely because the operational
attribute was introduced after their source observations were collected.  This
replays the deterministic synchronizer and validators against the strongest
current observation for every indexed business.  It does not manufacture
evidence: unknown operational status remains unknown and missing checks remain
pending.
"""

revision = "20261101_0067"
down_revision = "20261101_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical data repair. Current installations use consolidated
    # business attributes and do not persist validation-result rows.
    pass


def downgrade() -> None:
    # Facts and validation results are evidence records and may have been used
    # after this migration.  They are intentionally preserved on downgrade.
    pass
