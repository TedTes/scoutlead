"""store evidence-versioned search evaluations

Revision ID: 20261002_0031
Revises: 20261002_0030
Create Date: 2026-10-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20261002_0031"
down_revision = "20261002_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "business_search_evaluations" in inspector.get_table_names():
        return
    op.create_table(
        "business_search_evaluations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=False),
        sa.Column("contract_hash", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("criterion_results", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("missing_evidence", sa.JSON(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "contract_hash",
            "evidence_fingerprint",
            name="uq_business_search_evaluations_evidence",
        ),
    )
    op.create_index(
        "ix_business_search_evaluations_business_id",
        "business_search_evaluations",
        ["business_id"],
    )
    op.create_index(
        "ix_business_search_evaluations_contract_hash",
        "business_search_evaluations",
        ["contract_hash"],
    )
    op.create_index(
        "ix_business_search_evaluations_evidence_fingerprint",
        "business_search_evaluations",
        ["evidence_fingerprint"],
    )
    op.create_index(
        "ix_business_search_evaluations_status",
        "business_search_evaluations",
        ["status"],
    )
    op.create_index(
        "ix_business_search_evaluations_contract_status",
        "business_search_evaluations",
        ["contract_hash", "status"],
    )


def downgrade() -> None:
    op.drop_table("business_search_evaluations")
