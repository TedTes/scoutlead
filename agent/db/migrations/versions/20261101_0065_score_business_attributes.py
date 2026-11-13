"""score canonical business attributes independently from evidence confidence

Revision ID: 20261101_0065
Revises: 20261027_0064
Create Date: 2026-11-01

The canonical fact value remains the observed attribute. ``attribute_score``
normalizes the quality of that value onto 0-100, while the existing
``confidence`` column continues to mean confidence in the supporting evidence.
Unknown and unmapped values are deliberately left NULL.
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from business_attributes.attribute_scoring import score_attribute


revision = "20261101_0065"
down_revision = "20261027_0064"
branch_labels = None
depends_on = None


ATTRIBUTE_DEFINITIONS = (
    # key, label, value type, category, collector, extractor, direction, status
    ("http_status", "HTTP status", "number", "website", "website_dom", "http_status", "higher_is_opportunity", "active"),
    ("public_email_present", "Public email present", "boolean", "contact", "website_dom", "public_email_present", "false_is_opportunity", "active"),
    ("public_phone_present", "Public phone present", "boolean", "contact", "website_dom", "public_phone_present", "false_is_opportunity", "active"),
    ("contact_page_url", "Contact page URL", "text", "contact", "website_dom", "contact_page_url", "none", "active"),
    ("contact_form_url", "Contact form URL", "text", "contact", "website_dom", "contact_form_url", "none", "active"),
    ("booking_url", "Booking URL", "text", "conversion", "website_dom", "booking_url", "none", "active"),
    ("local_business_schema_present", "Local business schema present", "boolean", "local_seo", "website_dom", "local_business_schema_present", "false_is_opportunity", "active"),
    ("title_and_meta_present", "Title and meta description present", "boolean", "local_seo", "website_dom", "title_and_meta_present", "false_is_opportunity", "active"),
    # These are part of the catalog but remain disabled until their dedicated
    # collector has evidence. A draft definition can never qualify a lead.
    ("website_ownership", "Website ownership", "text", "website", None, None, "none", "draft"),
    ("review_recency_days", "Review recency", "number", "reputation", None, None, "higher_is_opportunity", "draft"),
    ("google_business_profile_present", "Google Business Profile present", "boolean", "local_seo", None, None, "false_is_opportunity", "draft"),
)


def upgrade() -> None:
    op.add_column("business_facts", sa.Column("attribute_score", sa.Float(), nullable=True))
    op.add_column("business_facts", sa.Column("score_version", sa.Integer(), nullable=True))
    op.add_column("business_facts", sa.Column("score_reason", sa.Text(), nullable=True))
    op.create_index(
        "ix_business_facts_attribute_score",
        "business_facts",
        ["attribute_score"],
    )

    bind = op.get_bind()
    _seed_attribute_definitions(bind)
    facts = sa.table(
        "business_facts",
        sa.column("id", sa.String),
        sa.column("fact_key", sa.String),
        sa.column("value_type", sa.String),
        sa.column("value_text", sa.Text),
        sa.column("value_number", sa.Float),
        sa.column("value_boolean", sa.Boolean),
        sa.column("attribute_score", sa.Float),
        sa.column("score_version", sa.Integer),
        sa.column("score_reason", sa.Text),
    )
    definitions = sa.table(
        "signal_definitions",
        sa.column("key", sa.String),
        sa.column("opportunity_direction", sa.String),
        sa.column("config", sa.JSON),
    )
    definition_rows = {
        row[0]: (row[1], row[2] or {})
        for row in bind.execute(
            sa.select(
                definitions.c.key,
                definitions.c.opportunity_direction,
                definitions.c.config,
            )
        )
    }
    rows = bind.execute(
        sa.select(
            facts.c.id,
            facts.c.fact_key,
            facts.c.value_type,
            facts.c.value_text,
            facts.c.value_number,
            facts.c.value_boolean,
        )
    )
    updates = []
    for row in rows:
        value = _value(row.value_type, row.value_text, row.value_number, row.value_boolean)
        direction, config = definition_rows.get(row.fact_key, (None, {}))
        scored = score_attribute(
            row.fact_key,
            value,
            opportunity_direction=direction,
            config=config,
        )
        updates.append(
            {
                "fact_id": row.id,
                "attribute_score": scored.score,
                "score_version": scored.version,
                "score_reason": scored.reason,
            }
        )
    if updates:
        bind.execute(
            facts.update()
            .where(facts.c.id == sa.bindparam("fact_id"))
            .values(
                attribute_score=sa.bindparam("attribute_score"),
                score_version=sa.bindparam("score_version"),
                score_reason=sa.bindparam("score_reason"),
            ),
            updates,
        )


def downgrade() -> None:
    op.drop_index("ix_business_facts_attribute_score", table_name="business_facts")
    op.drop_column("business_facts", "score_reason")
    op.drop_column("business_facts", "score_version")
    op.drop_column("business_facts", "attribute_score")


def _value(value_type, value_text, value_number, value_boolean):
    if value_type == "boolean":
        return value_boolean
    if value_type == "number":
        return value_number
    return value_text


def _seed_attribute_definitions(bind) -> None:
    definitions = sa.table(
        "signal_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("value_type", sa.String),
        sa.column("category", sa.String),
        sa.column("unit", sa.String),
        sa.column("status", sa.String),
        sa.column("collector_key", sa.String),
        sa.column("extractor_key", sa.String),
        sa.column("freshness_days", sa.Integer),
        sa.column("opportunity_direction", sa.String),
        sa.column("config", sa.JSON),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = set(bind.execute(sa.select(definitions.c.key)).scalars())
    now = datetime.now(timezone.utc)
    rows = []
    for key, label, value_type, category, collector, extractor, direction, status in ATTRIBUTE_DEFINITIONS:
        if key in existing:
            continue
        rows.append(
            {
                "id": f"attribute_{key}",
                "key": key,
                "label": label,
                "description": None,
                "value_type": value_type,
                "category": category,
                "unit": None,
                "status": status,
                "collector_key": collector,
                "extractor_key": extractor,
                "freshness_days": 30,
                "opportunity_direction": direction,
                "config": {
                    "auto_publish": status == "active",
                    "requires_validation": False,
                    "confidence": 95,
                },
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
        )
    if rows:
        bind.execute(definitions.insert(), rows)
