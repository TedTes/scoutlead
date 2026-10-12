"""add website quality signal definitions

Revision ID: 20261012_0043
Revises: 20261012_0042
Create Date: 2026-10-12
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261012_0043"
down_revision = "20261012_0042"
branch_labels = None
depends_on = None


WEBSITE_SIGNALS = (
    ("signal_uses_https", "uses_https", "HTTPS enabled", "boolean", "technical", None, "website_dom", "uses_https", 30, "false_is_opportunity", {}),
    ("signal_mobile_viewport_present", "mobile_viewport_present", "Mobile viewport present", "boolean", "performance", None, "website_dom", "mobile_viewport", 30, "false_is_opportunity", {}),
    ("signal_primary_cta_present", "primary_cta_present", "Primary call to action present", "boolean", "conversion", None, "website_dom", "primary_cta", 30, "false_is_opportunity", {}),
    ("signal_click_to_call_present", "click_to_call_present", "Click-to-call present", "boolean", "conversion", None, "website_dom", "click_to_call", 30, "false_is_opportunity", {}),
    ("signal_online_payment_or_financing_present", "online_payment_or_financing_present", "Online payment or financing present", "boolean", "conversion", None, "website_dom", "online_payment_or_financing", 30, "false_is_opportunity", {}),
    ("signal_service_area_pages_present", "service_area_pages_present", "Service-area content present", "boolean", "local_seo", None, "website_dom", "service_area_pages", 30, "false_is_opportunity", {}),
    ("signal_testimonials_present", "testimonials_present", "Testimonials present", "boolean", "trust", None, "website_dom", "testimonials", 30, "false_is_opportunity", {}),
    ("signal_privacy_policy_present", "privacy_policy_present", "Privacy policy present", "boolean", "trust", None, "website_dom", "privacy_policy", 30, "false_is_opportunity", {}),
    ("signal_complete_contact_details", "complete_contact_details", "Complete contact details", "boolean", "trust", None, "website_dom", "complete_contact_details", 30, "false_is_opportunity", {}),
    ("signal_mobile_performance_score", "mobile_performance_score", "Mobile performance score", "number", "performance", "score", "pagespeed_mobile", "pagespeed_performance_score", 30, "lower_is_opportunity", {"opportunity_threshold": 70}),
    ("signal_accessibility_score", "accessibility_score", "Accessibility score", "number", "accessibility", "score", "pagespeed_mobile", "pagespeed_accessibility_score", 30, "lower_is_opportunity", {"opportunity_threshold": 90}),
    ("signal_best_practices_score", "best_practices_score", "Best-practices score", "number", "technical", "score", "pagespeed_mobile", "pagespeed_best_practices_score", 30, "lower_is_opportunity", {"opportunity_threshold": 90}),
    ("signal_seo_score", "seo_score", "SEO score", "number", "local_seo", "score", "pagespeed_mobile", "pagespeed_seo_score", 30, "lower_is_opportunity", {"opportunity_threshold": 90}),
    ("signal_website_quality_score", "website_quality_score", "Website quality score", "number", "website", "score", "pagespeed_mobile", "pagespeed_quality_score", 30, "lower_is_opportunity", {"opportunity_threshold": 75}),
    ("signal_lcp_ms", "lcp_ms", "Largest Contentful Paint", "number", "performance", "ms", "pagespeed_mobile", "pagespeed_lcp_ms", 30, "higher_is_opportunity", {"opportunity_threshold": 2500}),
    ("signal_cls_score", "cls_score", "Cumulative Layout Shift", "number", "performance", "score", "pagespeed_mobile", "pagespeed_cls", 30, "higher_is_opportunity", {"opportunity_threshold": 0.1}),
    ("signal_inp_ms", "inp_ms", "Interaction to Next Paint", "number", "performance", "ms", "pagespeed_mobile", "pagespeed_inp_ms", 30, "higher_is_opportunity", {"opportunity_threshold": 200}),
    ("signal_tbt_ms", "tbt_ms", "Total Blocking Time", "number", "performance", "ms", "pagespeed_mobile", "pagespeed_tbt_ms", 30, "higher_is_opportunity", {"opportunity_threshold": 200}),
)


def _definitions_table():
    return sa.table(
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


def upgrade() -> None:
    definitions = _definitions_table()
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        definitions,
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
                "freshness_days": freshness_days,
                "opportunity_direction": direction,
                "config": {**config, "auto_publish": True, "confidence": 100},
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
                freshness_days,
                direction,
                config,
            ) in WEBSITE_SIGNALS
        ],
    )

    connection = op.get_bind()
    existing = list(
        connection.execute(
            sa.select(definitions.c.id, definitions.c.key, definitions.c.config).where(
                definitions.c.id.not_in([signal[0] for signal in WEBSITE_SIGNALS])
            )
        )
        .mappings()
    )
    for row in existing:
        config = dict(row["config"] or {})
        config["auto_publish"] = True
        config.setdefault("confidence", 100)
        values = {"config": config, "updated_at": now}
        if row["key"] == "domain_age_days":
            values["label"] = "Website domain age"
        connection.execute(
            definitions.update().where(definitions.c.id == row["id"]).values(**values)
        )


def downgrade() -> None:
    definitions = _definitions_table()
    connection = op.get_bind()
    connection.execute(
        definitions.delete().where(
            definitions.c.id.in_([signal[0] for signal in WEBSITE_SIGNALS])
        )
    )
    existing = list(
        connection.execute(
            sa.select(definitions.c.id, definitions.c.key, definitions.c.config)
        ).mappings()
    )
    for row in existing:
        config = dict(row["config"] or {})
        config.pop("auto_publish", None)
        config.pop("confidence", None)
        values = {"config": config}
        if row["key"] == "domain_age_days":
            values["label"] = "Domain age"
        connection.execute(
            definitions.update().where(definitions.c.id == row["id"]).values(**values)
        )
