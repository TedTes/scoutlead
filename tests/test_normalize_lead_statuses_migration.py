from __future__ import annotations

import importlib

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_normalizes_workflow_only_lead_statuses(monkeypatch) -> None:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    leads = sa.Table(
        "leads",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(64), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            leads.insert(),
            [
                {"id": "contacted", "status": "contacted"},
                {"id": "shortlisted", "status": "shortlisted"},
                {"id": "already-valid", "status": "responded"},
            ],
        )
        migration = importlib.import_module(
            "db.migrations.versions.20261113_0095_normalize_lead_statuses"
        )
        monkeypatch.setattr(
            migration,
            "op",
            Operations(MigrationContext.configure(connection)),
        )

        migration.upgrade()
        migration.upgrade()

        statuses = dict(
            connection.execute(sa.select(leads.c.id, leads.c.status)).tuples().all()
        )

    assert statuses == {
        "contacted": "sent",
        "shortlisted": "qualified",
        "already-valid": "responded",
    }
