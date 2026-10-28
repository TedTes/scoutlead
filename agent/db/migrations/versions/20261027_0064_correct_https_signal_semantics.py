"""correct HTTPS signal semantics and invalidate stale facts

Revision ID: 20261027_0064
Revises: 20261026_0063
Create Date: 2026-10-27

The previous extractor treated a stored HTTP canonical URL as proof that HTTPS
was unavailable. Version the signal so collection jobs run again with explicit
HTTP and HTTPS probes, and prevent the old facts from matching audiences while
that validation is pending.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261027_0064"
down_revision = "20261026_0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("business_facts"):
        facts = sa.table(
            "business_facts",
            sa.column("fact_key", sa.String),
            sa.column("quality_state", sa.String),
        )
        bind.execute(
            facts.update()
            .where(facts.c.fact_key == "uses_https")
            .values(quality_state="staged")
        )

    if inspector.has_table("signal_definitions"):
        definitions = sa.table(
            "signal_definitions",
            sa.column("id", sa.String),
            sa.column("key", sa.String),
            sa.column("version", sa.Integer),
            sa.column("config", sa.JSON),
        )
        rows = bind.execute(
            sa.select(
                definitions.c.id,
                definitions.c.version,
                definitions.c.config,
            ).where(definitions.c.key == "uses_https")
        ).mappings()
        for row in rows:
            config = dict(row["config"] or {})
            if int(config.get("protocol_evidence_version") or 0) >= 1:
                continue
            config["https_semantics"] = "available"
            config["protocol_evidence_version"] = 1
            bind.execute(
                definitions.update()
                .where(definitions.c.id == row["id"])
                .values(version=int(row["version"] or 1) + 1, config=config)
            )


def downgrade() -> None:
    # The previous false HTTPS facts cannot be safely republished.
    pass
