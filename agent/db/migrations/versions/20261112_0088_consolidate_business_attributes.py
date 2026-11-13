"""consolidate business evidence into business attributes

Revision ID: 20261112_0088
Revises: 20261112_0087
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert


revision = "20261112_0088"
down_revision = "20261112_0087"
branch_labels = None
depends_on = None


RETIRED_TABLES = (
    "business_fact_changes",
    "fact_claims",
    "validation_results",
    "business_search_evaluations",
    "business_facts",
    "source_observations",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Retiring the legacy evidence tables requires an ACCESS EXCLUSIVE
        # lock. Normal API reads can briefly hold weaker locks, so wait for
        # those transactions instead of failing the entire transactional
        # migration after the release workflow's short default timeout.
        bind.execute(sa.text("SET LOCAL lock_timeout = '120s'"))
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "business_attributes" not in tables:
        op.create_table(
            "business_attributes",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column(
                "business_id",
                sa.String(length=64),
                sa.ForeignKey("businesses.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("row_type", sa.String(length=32), nullable=False),
            sa.Column("attribute_key", sa.String(length=255), nullable=False),
            sa.Column(
                "signal_definition_id",
                sa.String(length=64),
                sa.ForeignKey("signal_definitions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("value_type", sa.String(length=16), nullable=False),
            sa.Column("value_text", sa.Text(), nullable=True),
            sa.Column("value_number", sa.Float(), nullable=True),
            sa.Column("value_boolean", sa.Boolean(), nullable=True),
            sa.Column("value_json", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=False),
            sa.Column("attribute_score", sa.Float(), nullable=True),
            sa.Column("score_version", sa.Integer(), nullable=True),
            sa.Column("score_reason", sa.Text(), nullable=True),
            sa.Column("resolution_state", sa.String(length=32), nullable=False),
            sa.Column("supporting_evidence_ids", sa.JSON(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source", sa.String(length=255), nullable=True),
            sa.Column("source_external_id", sa.String(length=255), nullable=True),
            sa.Column("source_query_signature", sa.String(length=500), nullable=True),
            sa.Column("source_content_hash", sa.String(length=64), nullable=True),
            sa.Column("source_url", sa.String(length=1000), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("resolver_version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "business_id",
                "row_type",
                "attribute_key",
                name="uq_business_attributes_business_type_key",
            ),
        )
        for name, columns in (
            ("ix_business_attributes_business_id", ["business_id"]),
            ("ix_business_attributes_row_type", ["row_type"]),
            ("ix_business_attributes_attribute_key", ["attribute_key"]),
            ("ix_business_attributes_signal_definition_id", ["signal_definition_id"]),
            ("ix_business_attributes_resolution_state", ["resolution_state"]),
            ("ix_business_attributes_source", ["source"]),
            ("ix_business_attributes_key_text", ["attribute_key", "value_text"]),
            ("ix_business_attributes_key_number", ["attribute_key", "value_number"]),
            ("ix_business_attributes_key_boolean", ["attribute_key", "value_boolean"]),
            ("ix_business_attributes_business_observed", ["business_id", "observed_at"]),
            ("ix_business_attributes_source_hash", ["source", "source_content_hash"]),
        ):
            op.create_index(name, "business_attributes", columns)

    tables = set(sa.inspect(bind).get_table_names())
    metadata = sa.MetaData()
    attributes = sa.Table("business_attributes", metadata, autoload_with=bind)
    observations_by_id: dict[str, dict[str, object]] = {}
    claim_evidence_by_id: dict[str, str] = {}

    if "source_observations" in tables:
        observations = sa.Table("source_observations", metadata, autoload_with=bind)
        observation_rows = [dict(row) for row in bind.execute(sa.select(observations)).mappings()]
        observations_by_id = {str(row["id"]): row for row in observation_rows}
        _bulk_insert(
            bind,
            attributes,
            [
                {
                    "id": row["id"],
                    "business_id": row["business_id"],
                    "row_type": "evidence",
                    "attribute_key": f"source:{row['id']}",
                    "signal_definition_id": None,
                    "value_type": "json",
                    "value_text": None,
                    "value_number": None,
                    "value_boolean": None,
                    "value_json": row.get("raw_payload") or {},
                    "confidence": 100,
                    "attribute_score": None,
                    "score_version": None,
                    "score_reason": None,
                    "resolution_state": "observed",
                    "supporting_evidence_ids": [],
                    "observed_at": row["observed_at"],
                    "expires_at": None,
                    "source": row.get("source"),
                    "source_external_id": row.get("external_id"),
                    "source_query_signature": row.get("query_signature"),
                    "source_content_hash": row.get("content_hash"),
                    "source_url": row.get("source_url"),
                    "evidence": row.get("raw_payload") or {},
                    "resolver_version": 1,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in observation_rows
            ],
        )

    if "fact_claims" in tables:
        claims = sa.Table("fact_claims", metadata, autoload_with=bind)
        claim_evidence_by_id = {
            str(row["id"]): str(row["source_observation_id"])
            for row in bind.execute(
                sa.select(claims.c.id, claims.c.source_observation_id)
            ).mappings()
            if row.get("source_observation_id")
        }

    if "business_facts" in tables:
        facts = sa.Table("business_facts", metadata, autoload_with=bind)
        migrated_attributes: list[dict[str, object]] = []
        for row in bind.execute(sa.select(facts)).mappings():
            fact = dict(row)
            evidence_id = fact.get("source_observation_id")
            evidence = observations_by_id.get(str(evidence_id), {}) if evidence_id else {}
            supporting_evidence_ids: list[str] = []
            for candidate in [
                evidence_id,
                *(
                    claim_evidence_by_id.get(str(claim_id))
                    for claim_id in (fact.get("supporting_claim_ids") or [])
                ),
            ]:
                if candidate and candidate not in supporting_evidence_ids:
                    supporting_evidence_ids.append(str(candidate))
            migrated_attributes.append(
                {
                    "id": fact["id"],
                    "business_id": fact["business_id"],
                    "row_type": "attribute",
                    "attribute_key": fact["fact_key"],
                    "signal_definition_id": fact.get("signal_definition_id"),
                    "value_type": fact["value_type"],
                    "value_text": fact.get("value_text"),
                    "value_number": fact.get("value_number"),
                    "value_boolean": fact.get("value_boolean"),
                    "value_json": None,
                    "confidence": fact["confidence"],
                    "attribute_score": fact.get("attribute_score"),
                    "score_version": fact.get("score_version"),
                    "score_reason": fact.get("score_reason"),
                    "resolution_state": fact.get("resolution_state") or "unknown",
                    "supporting_evidence_ids": supporting_evidence_ids,
                    "observed_at": fact["observed_at"],
                    "expires_at": fact.get("expires_at"),
                    "source": evidence.get("source"),
                    "source_external_id": evidence.get("external_id"),
                    "source_query_signature": evidence.get("query_signature"),
                    "source_content_hash": evidence.get("content_hash"),
                    "source_url": evidence.get("source_url"),
                    "evidence": evidence.get("raw_payload") or {},
                    "resolver_version": fact.get("resolver_version") or 1,
                    "created_at": fact["created_at"],
                    "updated_at": fact["updated_at"],
                }
            )
        _bulk_insert(bind, attributes, migrated_attributes)

    if "business_niche_memberships" in tables:
        membership_columns = {
            column["name"]
            for column in sa.inspect(bind).get_columns("business_niche_memberships")
        }
        if "source_observation_id" in membership_columns:
            with op.batch_alter_table("business_niche_memberships") as batch:
                batch.drop_column("source_observation_id")

    if "seed_batches" in tables:
        seed_columns = {
            column["name"] for column in sa.inspect(bind).get_columns("seed_batches")
        }
        if (
            "source_observation_count" in seed_columns
            and "evidence_record_count" not in seed_columns
        ):
            with op.batch_alter_table("seed_batches") as batch:
                batch.alter_column(
                    "source_observation_count",
                    new_column_name="evidence_record_count",
                    existing_type=sa.Integer(),
                    existing_nullable=False,
                )

    tables = set(sa.inspect(bind).get_table_names())
    for table_name in RETIRED_TABLES:
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    raise RuntimeError(
        "20261112_0088 is intentionally irreversible: retired evidence tables were "
        "consolidated into business_attributes. Restore from a backup if rollback is required."
    )


def _bulk_insert(
    bind: sa.Connection,
    table: sa.Table,
    rows: list[dict[str, object]],
    *,
    chunk_size: int = 1000,
) -> None:
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        if not chunk:
            continue
        if bind.dialect.name == "postgresql":
            statement = postgresql_insert(table).values(chunk)
            excluded = statement.excluded
            bind.execute(
                statement.on_conflict_do_update(
                    index_elements=["business_id", "row_type", "attribute_key"],
                    set_={
                        column.name: excluded[column.name]
                        for column in table.columns
                        if column.name not in {"id", "created_at"}
                    },
                )
            )
            continue
        if bind.dialect.name == "sqlite":
            statement = sqlite_insert(table).values(chunk)
            excluded = statement.excluded
            bind.execute(
                statement.on_conflict_do_update(
                    index_elements=["business_id", "row_type", "attribute_key"],
                    set_={
                        column.name: excluded[column.name]
                        for column in table.columns
                        if column.name not in {"id", "created_at"}
                    },
                )
            )
            continue

        # The deployed databases are PostgreSQL and tests use SQLite. Keep a
        # portable fallback so the migration remains deterministic elsewhere.
        for row in chunk:
            identity = sa.and_(
                table.c.business_id == row["business_id"],
                table.c.row_type == row["row_type"],
                table.c.attribute_key == row["attribute_key"],
            )
            existing_id = bind.scalar(sa.select(table.c.id).where(identity))
            if existing_id is None:
                bind.execute(table.insert().values(**row))
                continue
            bind.execute(
                table.update()
                .where(table.c.id == existing_id)
                .values(
                    **{
                        key: value
                        for key, value in row.items()
                        if key not in {"id", "created_at"}
                    }
                )
            )
