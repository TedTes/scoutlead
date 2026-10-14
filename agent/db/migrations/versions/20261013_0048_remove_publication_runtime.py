"""remove publication from the runtime search path

Revision ID: 20261013_0048
Revises: 20261013_0047
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_0048"
down_revision = "20261013_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the legacy column and tables for one deployment so old API and worker
    # processes can finish while the new runtime stops reading and writing them.
    op.alter_column(
        "audience_results",
        "publication_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.execute(
        """
        UPDATE queue_jobs
        SET status = 'canceled',
            last_error = 'Publication pipeline removed',
            updated_at = CURRENT_TIMESTAMP
        WHERE type = 'business.publication_evaluate'
          AND status IN ('queued', 'running')
        """
    )
    op.execute(
        """
        UPDATE pipeline_outbox_events
        SET status = 'published',
            published_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE topic = 'business.publication_changed'
          AND status IN ('pending', 'publishing')
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM audience_results WHERE publication_id IS NULL")
    op.alter_column(
        "audience_results",
        "publication_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
