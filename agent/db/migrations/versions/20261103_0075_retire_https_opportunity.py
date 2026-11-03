"""retire HTTPS as a lead opportunity

Revision ID: 20261103_0075
Revises: 20261103_0074
Create Date: 2026-11-03

Protocol information may remain in raw website observations for diagnostics,
but it must not qualify an audience, contribute to an opportunity score, or
appear as an outreach pitch.
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261103_0075"
down_revision = "20261103_0074"
branch_labels = None
depends_on = None

RETIRED_KEY = "uses_https"
WEBSITE_UPGRADE_WEIGHTS = {
    "mobile_viewport_present": 0.15,
    "website_quality_score": 0.25,
    "performance_score": 0.25,
    "accessibility_score": 0.15,
    "best_practices_score": 0.20,
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    metadata = sa.MetaData()
    now = datetime.now(timezone.utc)

    definition_ids: list[str] = []
    if inspector.has_table("signal_definitions"):
        definitions = sa.Table("signal_definitions", metadata, autoload_with=bind)
        definition_ids = [
            str(value)
            for value in bind.execute(
                sa.select(definitions.c.id).where(definitions.c.key == RETIRED_KEY)
            ).scalars()
        ]
        values = {"status": "inactive"}
        if "updated_at" in definitions.c:
            values["updated_at"] = now
        if "version" in definitions.c:
            values["version"] = definitions.c.version + 1
        bind.execute(
            definitions.update()
            .where(definitions.c.key == RETIRED_KEY)
            .values(**values)
        )

    if definition_ids and inspector.has_table("service_signal_mappings"):
        mappings = sa.Table(
            "service_signal_mappings", metadata, autoload_with=bind
        )
        bind.execute(
            mappings.delete().where(
                mappings.c.signal_definition_id.in_(definition_ids)
            )
        )

    if inspector.has_table("service_definitions"):
        services = sa.Table("service_definitions", metadata, autoload_with=bind)
        values = {
            "description": (
                "A verified website has measurable mobile, quality, performance, "
                "accessibility, or usability gaps."
            )
        }
        if "updated_at" in services.c:
            values["updated_at"] = now
        if "version" in services.c:
            values["version"] = services.c.version + 1
        bind.execute(
            services.update()
            .where(services.c.key == "website_upgrade")
            .values(**values)
        )
        if (
            inspector.has_table("signal_definitions")
            and inspector.has_table("service_signal_mappings")
        ):
            definitions = sa.Table(
                "signal_definitions", metadata, autoload_with=bind,
                extend_existing=True,
            )
            mappings = sa.Table(
                "service_signal_mappings", metadata, autoload_with=bind,
                extend_existing=True,
            )
            service_id = bind.execute(
                sa.select(services.c.id).where(
                    services.c.key == "website_upgrade"
                )
            ).scalar_one_or_none()
            if service_id is not None:
                for key, weight in WEBSITE_UPGRADE_WEIGHTS.items():
                    definition_id = bind.execute(
                        sa.select(definitions.c.id).where(definitions.c.key == key)
                    ).scalar_one_or_none()
                    if definition_id is None:
                        continue
                    bind.execute(
                        mappings.update()
                        .where(
                            mappings.c.service_definition_id == service_id,
                            mappings.c.signal_definition_id == definition_id,
                        )
                        .values(weight=weight)
                    )

    if inspector.has_table("territories"):
        territories = sa.Table("territories", metadata, autoload_with=bind)
        if "signal_keys" in territories.c:
            rows = bind.execute(
                sa.select(territories.c.id, territories.c.signal_keys)
            ).mappings()
            for row in rows:
                original = list(row["signal_keys"] or [])
                cleaned = [key for key in original if key != RETIRED_KEY]
                if cleaned == original:
                    continue
                values = {"signal_keys": cleaned}
                if "updated_at" in territories.c:
                    values["updated_at"] = now
                bind.execute(
                    territories.update()
                    .where(territories.c.id == row["id"])
                    .values(**values)
                )


def downgrade() -> None:
    # Restoring a retired sales opportunity could re-qualify leads from old
    # evidence, so downgrade intentionally leaves it inactive.
    pass
