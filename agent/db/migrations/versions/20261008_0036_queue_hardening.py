"""harden the durable job queue

Revision ID: 20261008_0036
Revises: 20261007_0035
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0036"
down_revision = "20261007_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("queue_jobs")}
    additions = {
        "idempotency_key": sa.Column("idempotency_key", sa.String(length=500)),
        "parent_run_id": sa.Column("parent_run_id", sa.String(length=64)),
        "locked_at": sa.Column("locked_at", sa.DateTime(timezone=True)),
        "dead_lettered_at": sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("queue_jobs", column)

    indexes = {index["name"] for index in inspector.get_indexes("queue_jobs")}
    if "ix_queue_jobs_parent_run_id" not in indexes:
        op.create_index("ix_queue_jobs_parent_run_id", "queue_jobs", ["parent_run_id"])
    if "ix_queue_jobs_poll" not in indexes:
        op.create_index(
            "ix_queue_jobs_poll",
            "queue_jobs",
            ["status", "run_after", "created_at"],
        )
    if "uq_queue_jobs_active_idempotency" not in indexes:
        op.create_index(
            "uq_queue_jobs_active_idempotency",
            "queue_jobs",
            ["idempotency_key"],
            unique=True,
            postgresql_where=sa.text(
                "idempotency_key IS NOT NULL AND status IN ('queued', 'running')"
            ),
        )


def downgrade() -> None:
    op.drop_index("uq_queue_jobs_active_idempotency", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_poll", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_parent_run_id", table_name="queue_jobs")
    op.drop_column("queue_jobs", "dead_lettered_at")
    op.drop_column("queue_jobs", "locked_at")
    op.drop_column("queue_jobs", "parent_run_id")
    op.drop_column("queue_jobs", "idempotency_key")
