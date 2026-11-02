"""make all business attribute scores point toward lead opportunity

Revision ID: 20261102_0070
Revises: 20261102_0069
Create Date: 2026-11-02

The physical ``attribute_score`` column is retained for compatibility, but its
meaning is now consistent everywhere: 0 means no opportunity and 100 means a
strong opportunity. Evidence confidence remains a separate value.
"""

from alembic import op
import sqlalchemy as sa

from business_facts.attribute_scoring import score_attribute


revision = "20261102_0070"
down_revision = "20261102_0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_facts") or not inspector.has_table(
        "signal_definitions"
    ):
        return

    metadata = sa.MetaData()
    facts = sa.Table("business_facts", metadata, autoload_with=bind)
    definitions = sa.Table("signal_definitions", metadata, autoload_with=bind)

    definition_rows = {}
    for row in bind.execute(
        sa.select(
            definitions.c.id,
            definitions.c.key,
            definitions.c.opportunity_direction,
            definitions.c.config,
        )
    ).mappings():
        config = dict(row["config"] or {})
        legacy_maximum = config.pop("audience_max_score", None)
        if (
            "audience_min_score" not in config
            and isinstance(legacy_maximum, (int, float))
        ):
            config["audience_min_score"] = round(
                100.0 - float(legacy_maximum),
                3,
            )
        if row["key"] == "website_status":
            values = config.get("opportunity_values")
            if isinstance(values, list):
                config["opportunity_values"] = [
                    value for value in values if value != "not_listed"
                ]
        definition_rows[row["key"]] = (
            row["opportunity_direction"],
            config,
        )
        values = {"config": config}
        if "version" in definitions.c.keys():
            values["version"] = definitions.c.version + 1
        bind.execute(
            definitions.update()
            .where(definitions.c.id == row["id"])
            .values(**values)
        )

    updates = []
    for row in bind.execute(
        sa.select(
            facts.c.id,
            facts.c.fact_key,
            facts.c.value_type,
            facts.c.value_text,
            facts.c.value_number,
            facts.c.value_boolean,
        )
    ).mappings():
        direction, config = definition_rows.get(row["fact_key"], (None, {}))
        scored = score_attribute(
            row["fact_key"],
            _value(row),
            opportunity_direction=direction,
            config=config,
        )
        updates.append(
            {
                "fact_id": row["id"],
                "opportunity_score": scored.score,
                "score_version": scored.version,
                "score_reason": scored.reason,
            }
        )
    for offset in range(0, len(updates), 1000):
        bind.execute(
            facts.update()
            .where(facts.c.id == sa.bindparam("fact_id"))
            .values(
                attribute_score=sa.bindparam("opportunity_score"),
                score_version=sa.bindparam("score_version"),
                score_reason=sa.bindparam("score_reason"),
            ),
            updates[offset : offset + 1000],
        )


def downgrade() -> None:
    # Scores may have been consumed after this migration. Restoring two
    # conflicting score directions would be unsafe.
    pass


def _value(row):
    if row["value_type"] == "boolean":
        return row["value_boolean"]
    if row["value_type"] == "number":
        return row["value_number"]
    return row["value_text"]
