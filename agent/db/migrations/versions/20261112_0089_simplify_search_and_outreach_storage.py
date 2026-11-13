"""simplify search, ingestion, and outreach storage

Revision ID: 20261112_0089
Revises: 20261112_0088
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20261112_0089"
down_revision = "20261112_0088"
branch_labels = None
depends_on = None


RETIRED_TABLES = (
    "outreach_events",
    "outreach_playbooks",
    "outreach_packages",
    "coverage_requests",
    "audience_runs",
    "source_item_decisions",
    "seed_batches",
    "outcome_models",
    "webhook_deliveries",
    "discovery_candidates",
    "campaign_memory",
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    _add_territory_match_state(tables)
    _migrate_latest_audience_results(bind, tables)
    _fold_source_item_decisions(bind, tables)
    _fold_outreach_packages_into_messages(bind, tables)

    if "business_niche_memberships" in tables:
        columns = _columns(bind, "business_niche_memberships")
        if "seed_batch_id" in columns:
            with op.batch_alter_table("business_niche_memberships") as batch:
                batch.drop_column("seed_batch_id")

    if "leads" in tables:
        with op.batch_alter_table("leads") as batch:
            batch.alter_column(
                "campaign_id",
                existing_type=sa.String(length=64),
                nullable=True,
            )

    tables = set(sa.inspect(bind).get_table_names())
    for table_name in RETIRED_TABLES:
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20261112_0089 is intentionally irreversible: redundant workflow tables "
        "were consolidated into territories, audience_results, source_items, leads, "
        "and messages. Restore from a backup if rollback is required."
    )


def _add_territory_match_state(tables: set[str]) -> None:
    if "territories" not in tables:
        return
    columns = _columns(op.get_bind(), "territories")
    additions = (
        ("match_state", sa.String(length=32), False, "'queued'"),
        ("match_requested_count", sa.Integer(), False, "25"),
        ("match_result_count", sa.Integer(), False, "0"),
        ("match_new_result_count", sa.Integer(), False, "0"),
        ("match_index_snapshot_at", sa.DateTime(timezone=True), True, None),
        ("match_deadline_at", sa.DateTime(timezone=True), True, None),
        ("match_started_at", sa.DateTime(timezone=True), True, None),
        ("match_completed_at", sa.DateTime(timezone=True), True, None),
        ("match_failure_reason", sa.Text(), True, None),
        ("outreach_campaign_id", sa.String(length=64), True, None),
    )
    for name, type_, nullable, default in additions:
        if name not in columns:
            op.add_column(
                "territories",
                sa.Column(name, type_, nullable=nullable, server_default=default),
            )
    with op.batch_alter_table("territories") as batch:
        if "outreach_campaign_id" not in columns:
            batch.create_foreign_key(
                "fk_territories_outreach_campaign_id_campaigns",
                "campaigns",
                ["outreach_campaign_id"],
                ["id"],
            )
            batch.create_index(
                "ix_territories_outreach_campaign_id", ["outreach_campaign_id"]
            )
        if "match_state" not in columns:
            batch.create_index("ix_territories_match_state", ["match_state"])


def _migrate_latest_audience_results(bind: sa.Connection, tables: set[str]) -> None:
    if not {"territories", "audience_results"}.issubset(tables):
        return
    metadata = sa.MetaData()
    territories = sa.Table("territories", metadata, autoload_with=bind)
    results = sa.Table("audience_results", metadata, autoload_with=bind)
    runs = (
        sa.Table("audience_runs", metadata, autoload_with=bind)
        if "audience_runs" in tables
        else None
    )

    latest_run_by_audience: dict[str, dict] = {}
    if runs is not None:
        rows = bind.execute(sa.select(runs).order_by(runs.c.created_at)).mappings()
        for row in rows:
            latest_run_by_audience[str(row["audience_id"])] = dict(row)
        for audience_id, row in latest_run_by_audience.items():
            bind.execute(
                territories.update()
                .where(territories.c.id == audience_id)
                .values(
                    match_state=row["state"],
                    match_requested_count=row["requested_count"],
                    match_result_count=row["result_count"],
                    match_new_result_count=row["new_result_count"],
                    match_index_snapshot_at=row["index_snapshot_at"],
                    match_deadline_at=row["deadline_at"],
                    match_started_at=row["started_at"],
                    match_completed_at=row["completed_at"],
                    match_failure_reason=row["failure_reason"],
                    outreach_campaign_id=row["outreach_campaign_id"],
                )
            )

    result_columns = _columns(bind, "audience_results")
    if "run_id" in result_columns and runs is not None:
        latest_run_ids = {str(row["id"]) for row in latest_run_by_audience.values()}
        all_results = [dict(row) for row in bind.execute(sa.select(results)).mappings()]
        keep_ids = {
            str(row["id"])
            for row in all_results
            if str(row.get("run_id")) in latest_run_ids
        }
        if keep_ids:
            bind.execute(results.delete().where(results.c.id.not_in(keep_ids)))
        else:
            bind.execute(results.delete())

    _fold_result_workflow_into_leads(bind, results, tables)

    # Avoid rank collisions while compacting the current result set.
    current_rows = [dict(row) for row in bind.execute(sa.select(results)).mappings()]
    for index, row in enumerate(current_rows, start=1):
        bind.execute(
            results.update().where(results.c.id == row["id"]).values(rank_position=-index)
        )
    by_audience: dict[str, list[dict]] = {}
    for row in current_rows:
        by_audience.setdefault(str(row["audience_id"]), []).append(row)
    for rows in by_audience.values():
        for rank, row in enumerate(sorted(rows, key=lambda item: item["rank_position"]), start=1):
            bind.execute(
                results.update().where(results.c.id == row["id"]).values(rank_position=rank)
            )

    result_columns = _columns(bind, "audience_results")
    retired_columns = [
        name
        for name in (
            "run_id",
            "review_status",
            "review_note",
            "reviewed_at",
            "shortlisted_at",
            "contacted_at",
        )
        if name in result_columns
    ]
    with op.batch_alter_table("audience_results") as batch:
        for constraint in (
            "uq_audience_results_run_business",
            "uq_audience_results_run_rank",
        ):
            try:
                batch.drop_constraint(constraint, type_="unique")
            except ValueError:
                pass
        for name in retired_columns:
            batch.drop_column(name)
        batch.create_unique_constraint(
            "uq_audience_results_audience_business", ["audience_id", "business_id"]
        )
        batch.create_unique_constraint(
            "uq_audience_results_audience_rank", ["audience_id", "rank_position"]
        )


def _fold_result_workflow_into_leads(
    bind: sa.Connection,
    results: sa.Table,
    tables: set[str],
) -> None:
    """Preserve durable user decisions before results become match-only rows."""

    if "leads" not in tables:
        return
    result_columns = _columns(bind, "audience_results")
    if "outreach_lead_id" not in result_columns:
        return
    workflow_columns = {
        "review_status",
        "review_note",
        "reviewed_at",
        "shortlisted_at",
        "contacted_at",
    } & result_columns
    if not workflow_columns:
        return

    leads = sa.Table("leads", sa.MetaData(), autoload_with=bind)
    lead_columns = set(leads.c.keys())
    for row in bind.execute(sa.select(results)).mappings():
        lead_id = row.get("outreach_lead_id")
        if not lead_id:
            continue
        values: dict[str, object] = {}
        for result_name, lead_name in (
            ("review_status", "review_status"),
            ("review_note", "review_note"),
            ("reviewed_at", "reviewed_at"),
            ("shortlisted_at", "shortlisted_at"),
            ("contacted_at", "last_contacted_at"),
        ):
            if result_name in workflow_columns and lead_name in lead_columns:
                value = row.get(result_name)
                if value is not None:
                    values[lead_name] = value
        if "status" in lead_columns:
            if row.get("contacted_at") is not None:
                # Contact workflow state is stored in last_contacted_at. Keep
                # the lead lifecycle status within the LeadStatus enum.
                values["status"] = "sent"
            elif row.get("shortlisted_at") is not None:
                # Shortlist workflow state is stored in shortlisted_at.
                values["status"] = "qualified"
        if values:
            bind.execute(
                leads.update().where(leads.c.id == lead_id).values(**values)
            )


def _fold_source_item_decisions(bind: sa.Connection, tables: set[str]) -> None:
    if "source_items" not in tables:
        return
    columns = _columns(bind, "source_items")
    additions = (
        ("decision_stage", sa.String(length=64)),
        ("decision", sa.String(length=64)),
        ("decision_reason", sa.Text()),
        ("decision_confidence", sa.Integer()),
        ("decision_details", sa.JSON()),
        ("decision_actor_type", sa.String(length=32)),
        ("decision_actor_id", sa.String(length=255)),
        ("decided_at", sa.DateTime(timezone=True)),
    )
    for name, type_ in additions:
        if name not in columns:
            op.add_column("source_items", sa.Column(name, type_, nullable=True))
    source_items = sa.Table("source_items", sa.MetaData(), autoload_with=bind)
    if "source_item_decisions" in tables:
        decisions = sa.Table("source_item_decisions", sa.MetaData(), autoload_with=bind)
        latest: dict[str, dict] = {}
        for row in bind.execute(sa.select(decisions).order_by(decisions.c.created_at)).mappings():
            latest[str(row["source_item_id"])] = dict(row)
        for source_item_id, row in latest.items():
            bind.execute(
                source_items.update()
                .where(source_items.c.id == source_item_id)
                .values(
                    decision_stage=row["stage"],
                    decision=row["decision"],
                    decision_reason=row["reason"],
                    decision_confidence=row["confidence"],
                    decision_details=row["details"] or {},
                    decision_actor_type=row["actor_type"],
                    decision_actor_id=row["actor_id"],
                    decided_at=row["created_at"],
                )
            )
    bind.execute(
        source_items.update()
        .where(source_items.c.decision_details.is_(None))
        .values(decision_details={})
    )
    with op.batch_alter_table("source_items") as batch:
        batch.alter_column("decision_details", existing_type=sa.JSON(), nullable=False)
        batch.create_index("ix_source_items_decision_stage", ["decision_stage"])
        batch.create_index("ix_source_items_decision", ["decision"])


def _fold_outreach_packages_into_messages(bind: sa.Connection, tables: set[str]) -> None:
    if "messages" not in tables:
        return
    columns = _columns(bind, "messages")
    additions = (
        ("audience_result_id", sa.String(length=64), True),
        ("generation_provider", sa.String(length=64), True),
        ("generation_model", sa.String(length=255), True),
        ("generation_usage", sa.JSON(), False),
        ("prompt_version", sa.Integer(), False),
        ("generation_context", sa.JSON(), False),
    )
    for name, type_, nullable in additions:
        if name not in columns:
            default = "{}" if name in {"generation_usage", "generation_context"} else "1" if name == "prompt_version" else None
            op.add_column(
                "messages",
                sa.Column(name, type_, nullable=nullable, server_default=default),
            )
    if "audience_result_id" not in columns:
        with op.batch_alter_table("messages") as batch:
            batch.create_foreign_key(
                "fk_messages_audience_result_id_audience_results",
                "audience_results",
                ["audience_result_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_index("ix_messages_audience_result_id", ["audience_result_id"])

    metadata = sa.MetaData()
    messages = sa.Table("messages", metadata, autoload_with=bind)
    if "outreach_packages" in tables:
        packages = sa.Table("outreach_packages", metadata, autoload_with=bind)
        results = sa.Table("audience_results", metadata, autoload_with=bind)
        leads = sa.Table("leads", metadata, autoload_with=bind)
        events_by_package: dict[str, list[dict]] = {}
        if "outreach_events" in tables:
            events = sa.Table("outreach_events", metadata, autoload_with=bind)
            for event in bind.execute(sa.select(events).order_by(events.c.created_at)).mappings():
                events_by_package.setdefault(str(event["package_id"]), []).append(
                    {
                        "id": event["id"],
                        "package_id": event["package_id"],
                        "channel": event["channel"],
                        "event_type": event["event_type"],
                        "variant_id": event["variant_id"],
                        "metadata": event["event_metadata"] or {},
                        "created_at": event["created_at"].isoformat(),
                    }
                )
        for package in bind.execute(sa.select(packages)).mappings():
            package = dict(package)
            result = bind.execute(
                sa.select(results).where(results.c.id == package["audience_result_id"])
            ).mappings().first()
            if not result or not result.get("outreach_lead_id"):
                continue
            lead = bind.execute(
                sa.select(leads).where(leads.c.id == result["outreach_lead_id"])
            ).mappings().first()
            if not lead:
                continue
            now = package["updated_at"] or package["created_at"]
            content = package["content"] or {}
            draft = content.get("message") if isinstance(content, dict) else None
            body = str(draft.get("body") or "Outreach context") if isinstance(draft, dict) else "Outreach context"
            bind.execute(
                messages.insert().values(
                    id=package["id"],
                    campaign_id=lead["campaign_id"],
                    product_id=lead["product_id"],
                    lead_id=lead["id"],
                    audience_result_id=package["audience_result_id"],
                    channel="outreach_package",
                    subject=None,
                    body=body,
                    personalization_notes=[],
                    approach_tag="outreach_package",
                    status="draft",
                    approval=None,
                    sent_at=None,
                    provider_message_id=None,
                    failure_reason=None,
                    generation_provider=package["provider"],
                    generation_model=package["model"],
                    generation_usage=package["usage"] or {},
                    prompt_version=package["prompt_version"],
                    generation_context={
                        "kind": "outreach_package",
                        "content": content,
                        "events": events_by_package.get(str(package["id"]), []),
                    },
                    created_at=package["created_at"],
                    updated_at=now,
                )
            )
    with op.batch_alter_table("messages") as batch:
        if "outreach_package_id" in _columns(bind, "messages"):
            batch.drop_column("outreach_package_id")
        batch.alter_column(
            "campaign_id", existing_type=sa.String(length=64), nullable=True
        )


def _columns(bind: sa.Connection, table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}
