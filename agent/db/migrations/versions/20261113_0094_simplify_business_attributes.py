"""store one self-contained row per business attribute

Revision ID: 20261113_0094
Revises: 20261113_0093
Create Date: 2026-11-13

Provider provenance already copied onto resolved attribute rows is retained.
Legacy evidence-only rows and their indirection columns are removed.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20261113_0094"
down_revision = "20261113_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "business_attributes" not in inspector.get_table_names():
        return

    metadata = sa.MetaData()
    attributes = sa.Table("business_attributes", metadata, autoload_with=bind)
    columns = set(attributes.c.keys())
    if "row_type" not in columns:
        return

    evidence_rows = {
        str(row["id"]): dict(row)
        for row in bind.execute(
            sa.select(attributes).where(attributes.c.row_type == "evidence")
        ).mappings()
    }
    attribute_rows = list(
        bind.execute(
            sa.select(attributes).where(attributes.c.row_type == "attribute")
        ).mappings()
    )
    for row in attribute_rows:
        supporting = row.get("supporting_evidence_ids") or []
        source_row = next(
            (
                evidence_rows[str(evidence_id)]
                for evidence_id in supporting
                if str(evidence_id) in evidence_rows
            ),
            None,
        )
        if source_row is None:
            continue
        values = {}
        for column in (
            "source",
            "source_external_id",
            "source_query_signature",
            "source_content_hash",
            "source_url",
            "evidence",
        ):
            if not row.get(column) and source_row.get(column) is not None:
                values[column] = source_row[column]
        if values:
            bind.execute(
                attributes.update()
                .where(attributes.c.id == row["id"])
                .values(**values)
            )

    bind.execute(attributes.delete().where(attributes.c.row_type != "attribute"))

    existing_indexes = {item["name"] for item in inspector.get_indexes("business_attributes")}
    for name in (
        "ix_business_attributes_row_type",
        "ix_business_attributes_resolution_state",
        "ix_business_attributes_source_hash",
        "ix_business_attributes_source",
        "ix_business_attributes_attribute_score",
    ):
        if name in existing_indexes:
            op.drop_index(name, table_name="business_attributes")

    unique_constraints = {
        item["name"] for item in inspector.get_unique_constraints("business_attributes")
    }
    with op.batch_alter_table("business_attributes") as batch:
        if "uq_business_attributes_business_type_key" in unique_constraints:
            batch.drop_constraint(
                "uq_business_attributes_business_type_key",
                type_="unique",
            )
        batch.alter_column("attribute_score", new_column_name="opportunity_score")
        batch.alter_column("source", new_column_name="source_provider")
        batch.alter_column("source_content_hash", new_column_name="evidence_hash")
        batch.drop_column("row_type")
        batch.drop_column("resolution_state")
        batch.drop_column("supporting_evidence_ids")
        batch.drop_column("resolver_version")
        batch.create_unique_constraint(
            "uq_business_attributes_business_key",
            ["business_id", "attribute_key"],
        )

    op.create_index(
        "ix_business_attributes_opportunity_score",
        "business_attributes",
        ["opportunity_score"],
    )
    op.create_index(
        "ix_business_attributes_source_provider",
        "business_attributes",
        ["source_provider"],
    )
    op.create_index(
        "ix_business_attributes_source_hash",
        "business_attributes",
        ["source_provider", "evidence_hash"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "20261113_0094 is intentionally irreversible: evidence-only rows were removed."
    )
