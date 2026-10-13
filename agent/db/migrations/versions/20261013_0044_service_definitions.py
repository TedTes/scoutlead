"""add dynamic services and multilingual signals

Revision ID: 20261013_0044
Revises: 20261012_0043
Create Date: 2026-10-13
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261013_0044"
down_revision = "20261012_0043"
branch_labels = None
depends_on = None


MULTILINGUAL_SIGNALS = (
    (
        "signal_html_language_present",
        "html_language_present",
        "HTML language declared",
        "boolean",
        "localization",
        None,
        "website_dom",
        "html_language_present",
        "false_is_opportunity",
        {},
    ),
    (
        "signal_hreflang_present",
        "hreflang_present",
        "Alternate languages declared",
        "boolean",
        "localization",
        None,
        "website_dom",
        "hreflang_present",
        "false_is_opportunity",
        {},
    ),
    (
        "signal_language_selector_present",
        "language_selector_present",
        "Language selector present",
        "boolean",
        "localization",
        None,
        "website_dom",
        "language_selector_present",
        "false_is_opportunity",
        {},
    ),
    (
        "signal_translated_page_count",
        "translated_page_count",
        "Translated page count",
        "number",
        "localization",
        "pages",
        "website_dom",
        "translated_page_count",
        "lower_is_opportunity",
        {"opportunity_threshold": 2},
    ),
    (
        "signal_market_language_supported",
        "market_language_supported",
        "Market language supported",
        "boolean",
        "localization",
        None,
        "website_dom",
        "market_language_supported",
        "false_is_opportunity",
        {},
    ),
)


SERVICES = (
    (
        "service_website_modernization",
        "website_modernization",
        "Website presence and modernization",
        "Missing, insecure, or low-quality website.",
        10,
        ("website_status", "website_quality_score", "best_practices_score", "uses_https"),
    ),
    (
        "service_lead_capture",
        "lead_capture",
        "Lead capture and conversion",
        "Missing contact paths, calls to action, or business details.",
        20,
        (
            "contact_form_present",
            "primary_cta_present",
            "click_to_call_present",
            "complete_contact_details",
        ),
    ),
    (
        "service_booking_payments",
        "booking_payments",
        "Quotes, booking, and payments",
        "Missing quote, scheduling, payment, or financing flows.",
        30,
        ("quote_or_booking_form_present", "online_payment_or_financing_present"),
    ),
    (
        "service_performance_accessibility",
        "performance_accessibility",
        "Mobile performance and accessibility",
        "Slow, unstable, inaccessible, or poorly adapted mobile experience.",
        40,
        (
            "accessibility_score",
            "mobile_performance_score",
            "mobile_viewport_present",
            "lcp_ms",
            "cls_score",
            "inp_ms",
            "tbt_ms",
        ),
    ),
    (
        "service_local_visibility",
        "local_visibility",
        "Local SEO and service-area visibility",
        "Weak search readiness or missing local service content.",
        50,
        ("seo_score", "service_area_pages_present"),
    ),
    (
        "service_reputation_trust",
        "reputation_trust",
        "Reputation and trust",
        "Weak reviews or missing customer and compliance signals.",
        60,
        (
            "google_rating",
            "google_review_count",
            "testimonials_present",
            "privacy_policy_present",
        ),
    ),
    (
        "service_multilingual_localization",
        "multilingual_localization",
        "Multilingual website localization",
        "Missing language declarations, alternate pages, or local-language support.",
        70,
        (
            "html_language_present",
            "hreflang_present",
            "language_selector_present",
            "translated_page_count",
            "market_language_supported",
        ),
    ),
)


def upgrade() -> None:
    op.create_table(
        "service_definitions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_service_definitions_key", "service_definitions", ["key"])
    op.create_index("ix_service_definitions_status", "service_definitions", ["status"])
    op.create_table(
        "service_signal_mappings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("service_definition_id", sa.String(length=64), nullable=False),
        sa.Column("signal_definition_id", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_definition_id"],
            ["service_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signal_definition_id"],
            ["signal_definitions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_definition_id",
            "signal_definition_id",
            name="uq_service_signal_mappings_service_signal",
        ),
    )
    op.create_index(
        "ix_service_signal_mappings_service_definition_id",
        "service_signal_mappings",
        ["service_definition_id"],
    )
    op.create_index(
        "ix_service_signal_mappings_signal_definition_id",
        "service_signal_mappings",
        ["signal_definition_id"],
    )
    op.add_column(
        "territories",
        sa.Column("service_keys", sa.JSON(), nullable=False, server_default="[]"),
    )

    now = datetime.now(timezone.utc)
    signal_definitions = sa.table(
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
    op.bulk_insert(
        signal_definitions,
        [
            {
                "id": signal_id,
                "key": key,
                "label": label,
                "description": None,
                "value_type": value_type,
                "category": category,
                "unit": unit,
                "status": "active",
                "collector_key": collector,
                "extractor_key": extractor,
                "freshness_days": 30,
                "opportunity_direction": direction,
                "config": {
                    **config,
                    "confidence": 100,
                    "requires_validation": True,
                },
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for (
                signal_id,
                key,
                label,
                value_type,
                category,
                unit,
                collector,
                extractor,
                direction,
                config,
            ) in MULTILINGUAL_SIGNALS
        ],
    )

    service_definitions = sa.table(
        "service_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("status", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        service_definitions,
        [
            {
                "id": service_id,
                "key": key,
                "label": label,
                "description": description,
                "status": "draft" if key == "multilingual_localization" else "active",
                "sort_order": sort_order,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            for service_id, key, label, description, sort_order, _ in SERVICES
        ],
    )

    connection = op.get_bind()
    signal_ids = dict(
        connection.execute(
            sa.select(signal_definitions.c.key, signal_definitions.c.id)
        ).all()
    )
    mappings = sa.table(
        "service_signal_mappings",
        sa.column("id", sa.String),
        sa.column("service_definition_id", sa.String),
        sa.column("signal_definition_id", sa.String),
        sa.column("weight", sa.Float),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = []
    for service_id, _, _, _, _, signal_keys in SERVICES:
        for index, signal_key in enumerate(signal_keys):
            signal_id = signal_ids.get(signal_key)
            if signal_id is None:
                continue
            rows.append(
                {
                    "id": f"mapping_{service_id.removeprefix('service_')}_{index + 1}",
                    "service_definition_id": service_id,
                    "signal_definition_id": signal_id,
                    "weight": 1.0,
                    "sort_order": index,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    op.bulk_insert(mappings, rows)


def downgrade() -> None:
    op.drop_column("territories", "service_keys")
    op.drop_table("service_signal_mappings")
    op.drop_table("service_definitions")
    signal_ids = [signal[0] for signal in MULTILINGUAL_SIGNALS]
    for table in ("fact_claims", "business_facts"):
        op.execute(
            sa.text(
                f"UPDATE {table} SET signal_definition_id = NULL "
                "WHERE signal_definition_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True, value=signal_ids))
        )
    op.execute(
        sa.text("DELETE FROM signal_definitions WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True, value=signal_ids)
        )
    )
