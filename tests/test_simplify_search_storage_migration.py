import importlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


RETIRED_TABLES = {
    "coverage_requests",
    "discovery_candidates",
    "source_item_decisions",
    "outreach_packages",
    "outreach_playbooks",
    "outreach_events",
    "outcome_models",
    "campaign_memory",
    "seed_batches",
    "webhook_deliveries",
    "audience_runs",
}


def test_simplification_preserves_current_state_and_drops_redundant_tables() -> None:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    campaigns = sa.Table(
        "campaigns", metadata, sa.Column("id", sa.String(64), primary_key=True)
    )
    territories = sa.Table(
        "territories", metadata, sa.Column("id", sa.String(64), primary_key=True)
    )
    leads = sa.Table(
        "leads",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("shortlisted_at", sa.DateTime(timezone=True)),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True)),
    )
    runs = sa.Table(
        "audience_runs",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("audience_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("new_result_count", sa.Integer(), nullable=False),
        sa.Column("index_snapshot_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("outreach_campaign_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    results = sa.Table(
        "audience_results",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("audience_id", sa.String(64), nullable=False),
        sa.Column("business_id", sa.String(64), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("match_snapshot", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("review_note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("shortlisted_at", sa.DateTime(timezone=True)),
        sa.Column("contacted_at", sa.DateTime(timezone=True)),
        sa.Column("outreach_lead_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "business_id", name="uq_audience_results_run_business"
        ),
        sa.UniqueConstraint(
            "run_id", "rank_position", name="uq_audience_results_run_rank"
        ),
    )
    source_items = sa.Table(
        "source_items", metadata, sa.Column("id", sa.String(64), primary_key=True)
    )
    source_decisions = sa.Table(
        "source_item_decisions",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_item_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("confidence", sa.Integer()),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    memberships = sa.Table(
        "business_niche_memberships",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("seed_batch_id", sa.String(64)),
    )
    messages = sa.Table(
        "messages",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column("product_id", sa.String(64), nullable=False),
        sa.Column("lead_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(500)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("personalization_notes", sa.JSON(), nullable=False),
        sa.Column("approach_tag", sa.String(255), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("approval", sa.JSON()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.String(255)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("outreach_package_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    packages = sa.Table(
        "outreach_packages",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workspace_id", sa.String(255)),
        sa.Column("audience_result_id", sa.String(64), nullable=False),
        sa.Column("business_id", sa.String(64), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255)),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    events = sa.Table(
        "outreach_events",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("package_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("variant_id", sa.String(120)),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table_name in RETIRED_TABLES - {
        "audience_runs",
        "source_item_decisions",
        "outreach_packages",
        "outreach_events",
    }:
        sa.Table(table_name, metadata, sa.Column("id", sa.String(64), primary_key=True))
    metadata.create_all(engine)

    now = datetime(2026, 11, 12, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(campaigns.insert(), {"id": "campaign_1"})
        connection.execute(territories.insert(), {"id": "audience_1"})
        connection.execute(
            leads.insert(),
            {
                "id": "lead_1",
                "campaign_id": "campaign_1",
                "product_id": "product_1",
                "status": "qualified",
                "review_status": "unreviewed",
            },
        )
        connection.execute(
            runs.insert(),
            [
                _run("run_old", "partial", now, result_count=1),
                _run("run_current", "ready", now, result_count=1),
            ],
        )
        connection.execute(
            results.insert(),
            [
                _result("result_old", "run_old", "business_old", now),
                {
                    **_result("result_current", "run_current", "business_1", now),
                    "review_status": "not_fit",
                    "review_note": "Not a fit",
                    "reviewed_at": now,
                    "shortlisted_at": now,
                    "contacted_at": now,
                    "outreach_lead_id": "lead_1",
                },
            ],
        )
        connection.execute(source_items.insert(), {"id": "source_item_1"})
        connection.execute(
            source_decisions.insert(),
            {
                "id": "decision_1",
                "source_item_id": "source_item_1",
                "stage": "identity",
                "decision": "accepted",
                "reason": "Structured provider entity",
                "confidence": 95,
                "details": {"provider": "google_places"},
                "actor_type": "system",
                "actor_id": None,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(memberships.insert(), {"id": "membership_1"})
        connection.execute(
            packages.insert(),
            {
                "id": "package_1",
                "workspace_id": "workspace_1",
                "audience_result_id": "result_current",
                "business_id": "business_1",
                "content": {"message": {"body": "Hello"}},
                "provider": "anthropic",
                "model": "claude",
                "usage": {"input_tokens": 10},
                "prompt_version": 3,
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            events.insert(),
            {
                "id": "event_1",
                "package_id": "package_1",
                "channel": "email",
                "event_type": "generated",
                "variant_id": None,
                "event_metadata": {},
                "created_at": now,
            },
        )

        migration = importlib.import_module(
            "db.migrations.versions.20261112_0089_simplify_search_and_outreach_storage"
        )
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        inspector = sa.inspect(connection)
        assert RETIRED_TABLES.isdisjoint(inspector.get_table_names())
        assert "run_id" not in _column_names(inspector, "audience_results")
        assert "review_status" not in _column_names(inspector, "audience_results")
        assert "seed_batch_id" not in _column_names(
            inspector, "business_niche_memberships"
        )

        current_territories = sa.Table(
            "territories", sa.MetaData(), autoload_with=connection
        )
        territory = connection.execute(sa.select(current_territories)).mappings().one()
        assert territory["match_state"] == "ready"
        assert territory["match_result_count"] == 1

        current_results = sa.Table(
            "audience_results", sa.MetaData(), autoload_with=connection
        )
        assert [row.id for row in connection.execute(sa.select(current_results))] == [
            "result_current"
        ]

        current_leads = sa.Table("leads", sa.MetaData(), autoload_with=connection)
        lead = connection.execute(sa.select(current_leads)).mappings().one()
        assert lead["review_status"] == "not_fit"
        assert lead["last_contacted_at"] is not None
        assert lead["status"] == "contacted"

        current_items = sa.Table(
            "source_items", sa.MetaData(), autoload_with=connection
        )
        item = connection.execute(sa.select(current_items)).mappings().one()
        assert item["decision"] == "accepted"
        assert item["decision_confidence"] == 95

        current_messages = sa.Table(
            "messages", sa.MetaData(), autoload_with=connection
        )
        message = connection.execute(
            sa.select(current_messages).where(current_messages.c.id == "package_1")
        ).mappings().one()
        assert message["channel"] == "outreach_package"
        assert message["audience_result_id"] == "result_current"
        assert message["generation_context"]["events"][0]["id"] == "event_1"


def _run(
    run_id: str,
    state: str,
    now: datetime,
    *,
    result_count: int,
) -> dict:
    return {
        "id": run_id,
        "audience_id": "audience_1",
        "state": state,
        "requested_count": 25,
        "result_count": result_count,
        "new_result_count": result_count,
        "index_snapshot_at": now,
        "deadline_at": now,
        "started_at": now,
        "completed_at": now,
        "failure_reason": None,
        "outreach_campaign_id": "campaign_1",
        "created_at": now,
        "updated_at": now,
    }


def _result(result_id: str, run_id: str, business_id: str, now: datetime) -> dict:
    return {
        "id": result_id,
        "run_id": run_id,
        "audience_id": "audience_1",
        "business_id": business_id,
        "rank_position": 1,
        "is_new": True,
        "match_snapshot": {"title": business_id},
        "review_status": "unreviewed",
        "review_note": None,
        "reviewed_at": None,
        "shortlisted_at": None,
        "contacted_at": None,
        "outreach_lead_id": None,
        "created_at": now,
        "updated_at": now,
    }


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}
