"""detach the retired publication schema from the runtime

Revision ID: 20261014_0050
Revises: 20261014_0049
"""

from alembic import op


revision = "20261014_0050"
down_revision = "20261014_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_audience_results_publication_id", table_name="audience_results")
    op.drop_constraint(
        "audience_results_publication_id_fkey",
        "audience_results",
        type_="foreignkey",
    )
    op.drop_column("audience_results", "publication_id")
    op.drop_table("pipeline_outbox_events")

    # Keep the final compatibility table for one more deployment. The previous
    # application version can still hold a long-lived ACCESS SHARE lock while
    # migrations run, which makes DROP TABLE block the rolling deployment.
    # Nothing in the current runtime reads or writes this table.


def downgrade() -> None:
    raise RuntimeError("The retired publication schema cannot be restored")
