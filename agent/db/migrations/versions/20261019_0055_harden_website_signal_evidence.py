"""harden website signal evidence publication

Revision ID: 20261019_0055
Revises: 20261016_0054
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0055"
down_revision = "20261016_0054"
branch_labels = None
depends_on = None


WEBSITE_SIGNAL_KEYS = (
    "contact_form_present",
    "quote_or_booking_form_present",
    "uses_https",
    "mobile_viewport_present",
    "primary_cta_present",
    "click_to_call_present",
    "online_payment_or_financing_present",
    "service_area_pages_present",
)


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
            .where(facts.c.fact_key.in_(WEBSITE_SIGNAL_KEYS))
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
            ).where(definitions.c.key.in_(WEBSITE_SIGNAL_KEYS))
        ).mappings()
        for row in rows:
            config = dict(row["config"] or {})
            config["requires_validation"] = True
            config["evidence_contract_version"] = 2
            bind.execute(
                definitions.update()
                .where(definitions.c.id == row["id"])
                .values(version=int(row["version"] or 1) + 1, config=config)
            )


def downgrade() -> None:
    # Previously published heuristic facts cannot be safely reconstructed.
    pass
