"""decouple client saved searches from data collection

Revision ID: 20261112_0085
Revises: 20261111_0084
Create Date: 2026-11-12
"""

from alembic import op


revision = "20261112_0085"
down_revision = "20261111_0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Runs created by the old coupled workflow can otherwise remain in
    # waiting_validation forever after client searches stop driving collection.
    op.execute(
        """
        UPDATE audience_runs
        SET state = 'partial',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            failure_reason = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE state IN ('queued', 'matching', 'expanding', 'waiting_validation')
        """
    )
    op.execute(
        """
        UPDATE queue_jobs
        SET status = 'canceled',
            locked_at = NULL,
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            last_error = 'Client saved searches no longer run collection jobs',
            updated_at = CURRENT_TIMESTAMP
        WHERE type = 'audience.run'
          AND status IN ('queued', 'running')
        """
    )
    op.execute(
        """
        UPDATE coverage_requests
        SET status = 'failed',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            failure_reason = 'Coverage collection moved to admin-controlled jobs',
            updated_at = CURRENT_TIMESTAMP
        WHERE status IN ('queued', 'processing')
        """
    )


def downgrade() -> None:
    # Terminal historical work cannot be reconstructed safely.
    pass
