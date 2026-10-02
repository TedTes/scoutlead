"""add durable source items and decisions

Revision ID: 20261002_0028
Revises: 20261002_0027
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0028"
down_revision = "20261002_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("source_items"):
        op.create_table(
            "source_items",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("segment_id", sa.String(length=64), nullable=False),
            sa.Column("job_id", sa.String(length=64), nullable=True),
            sa.Column("provider_id", sa.String(length=255), nullable=False),
            sa.Column("external_id", sa.String(length=500), nullable=True),
            sa.Column("query", sa.Text(), nullable=False),
            sa.Column("source_url", sa.String(length=2000), nullable=True),
            sa.Column("title", sa.String(length=1000), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("state", sa.String(length=64), nullable=False),
            sa.Column("business_id", sa.String(length=64), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["queue_jobs.id"]),
            sa.ForeignKeyConstraint(["segment_id"], ["business_index_segments.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "segment_id",
                "provider_id",
                "content_hash",
                name="uq_source_items_segment_provider_content",
            ),
        )
        for column in (
            "segment_id",
            "job_id",
            "provider_id",
            "external_id",
            "content_hash",
            "state",
            "business_id",
        ):
            op.create_index(op.f(f"ix_source_items_{column}"), "source_items", [column])
        op.create_index(
            "ix_source_items_segment_state", "source_items", ["segment_id", "state"]
        )
        op.create_index(
            "ix_source_items_provider_fetched",
            "source_items",
            ["provider_id", "fetched_at"],
        )

    inspector = sa.inspect(bind)
    if not inspector.has_table("source_item_decisions"):
        op.create_table(
            "source_item_decisions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("source_item_id", sa.String(length=64), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("decision", sa.String(length=64), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("actor_type", sa.String(length=32), nullable=False),
            sa.Column("actor_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("source_item_id", "stage", "decision"):
            op.create_index(
                op.f(f"ix_source_item_decisions_{column}"),
                "source_item_decisions",
                [column],
            )
        op.create_index(
            "ix_source_item_decisions_item_stage_created",
            "source_item_decisions",
            ["source_item_id", "stage", "created_at"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("source_item_decisions"):
        op.drop_table("source_item_decisions")
    if inspector.has_table("source_items"):
        op.drop_table("source_items")
