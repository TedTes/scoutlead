import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_decouple_search_collection_migration_closes_legacy_active_work() -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()

    def timestamp_columns():
        return (
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    sa.Table(
        "audience_runs",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamp_columns(),
    )
    sa.Table(
        "queue_jobs",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        *timestamp_columns(),
    )
    sa.Table(
        "coverage_requests",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamp_columns(),
    )
    metadata.create_all(engine)
    migration = importlib.import_module(
        "db.migrations.versions.20261112_0085_decouple_search_from_collection"
    )

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO audience_runs (id, state) VALUES "
            "('active', 'waiting_validation'), ('done', 'ready')"
        )
        connection.exec_driver_sql(
            "INSERT INTO queue_jobs (id, type, status) VALUES "
            "('audience', 'audience.run', 'queued'), "
            "('collection', 'business_index.refresh', 'queued')"
        )
        connection.exec_driver_sql(
            "INSERT INTO coverage_requests (id, status) VALUES "
            "('active', 'processing'), ('done', 'completed')"
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        runs = {
            row[0]: row[1]
            for row in connection.exec_driver_sql(
                "SELECT id, state FROM audience_runs"
            )
        }
        jobs = {
            row[0]: row[1]
            for row in connection.exec_driver_sql("SELECT id, status FROM queue_jobs")
        }
        coverage = {
            row[0]: row[1]
            for row in connection.exec_driver_sql(
                "SELECT id, status FROM coverage_requests"
            )
        }

        assert runs == {"active": "partial", "done": "ready"}
        assert jobs == {"audience": "canceled", "collection": "queued"}
        assert coverage == {"active": "failed", "done": "completed"}
