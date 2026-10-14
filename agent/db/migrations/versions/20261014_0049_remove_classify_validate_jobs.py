"""remove obsolete classification and business-validation jobs

Revision ID: 20261014_0049
Revises: 20261013_0048
"""

from alembic import op


revision = "20261014_0049"
down_revision = "20261013_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve unfinished work by converting it to the replacement pipeline stages.
    # Clearing the old idempotency keys avoids collisions with jobs already queued by
    # the new runtime during a rolling deployment.
    op.execute(
        """
        UPDATE queue_jobs
        SET type = 'business.identity_resolve',
            idempotency_key = NULL,
            status = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN 'queued'
                ELSE status
            END,
            attempts = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN 0
                ELSE attempts
            END,
            run_after = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN CURRENT_TIMESTAMP
                ELSE run_after
            END,
            locked_at = NULL,
            dead_lettered_at = NULL,
            last_error = NULL,
            completed_at = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN NULL
                ELSE completed_at
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE type = 'source_item.classify'
        """
    )
    op.execute(
        """
        UPDATE queue_jobs
        SET type = 'business.opportunity_audit',
            idempotency_key = NULL,
            status = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN 'queued'
                ELSE status
            END,
            attempts = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN 0
                ELSE attempts
            END,
            run_after = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN CURRENT_TIMESTAMP
                ELSE run_after
            END,
            locked_at = NULL,
            dead_lettered_at = NULL,
            last_error = NULL,
            completed_at = CASE
                WHEN status IN ('running', 'failed', 'dead_letter') THEN NULL
                ELSE completed_at
            END,
            updated_at = CURRENT_TIMESTAMP
        WHERE type = 'business.validate'
        """
    )
    op.execute(
        """
        UPDATE source_items
        SET state = CASE
            WHEN state = 'validation_queued' THEN 'resolution_queued'
            WHEN state IN ('identity_resolved', 'validating', 'validated') THEN 'audit_pending'
            ELSE state
        END,
        updated_at = CURRENT_TIMESTAMP
        WHERE state IN ('validation_queued', 'identity_resolved', 'validating', 'validated')
        """
    )
    op.execute(
        """
        UPDATE source_item_decisions
        SET stage = CASE WHEN stage = 'validation' THEN 'identity' ELSE stage END,
            decision = CASE WHEN decision = 'validated' THEN 'resolved' ELSE decision END,
            updated_at = CURRENT_TIMESTAMP
        WHERE stage = 'validation' OR decision = 'validated'
        """
    )
    op.execute(
        """
        UPDATE run_pipeline_events
        SET job_id = NULL
        WHERE job_id IN (
            SELECT id FROM queue_jobs
            WHERE type IN ('campaign.run', 'search.eligibility_match')
        )
        """
    )
    op.execute(
        """
        UPDATE source_items
        SET job_id = NULL
        WHERE job_id IN (
            SELECT id FROM queue_jobs
            WHERE type IN ('campaign.run', 'search.eligibility_match')
        )
        """
    )
    op.execute(
        """
        DELETE FROM queue_jobs
        WHERE type IN ('campaign.run', 'search.eligibility_match')
        """
    )


def downgrade() -> None:
    # The original job type cannot be inferred after it has been migrated.
    pass
