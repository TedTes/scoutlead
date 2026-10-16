"""repair missing core service catalog rows

Revision ID: 20261015_0052
Revises: 20261014_0051
Create Date: 2026-10-15
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20261015_0052"
down_revision = "20261014_0051"
branch_labels = None
depends_on = None


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
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    services = sa.table(
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
    existing_service_keys = set(bind.execute(sa.select(services.c.key)).scalars())
    missing_services = [
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
        if key not in existing_service_keys
    ]
    if missing_services:
        bind.execute(services.insert(), missing_services)

    signals = sa.table(
        "signal_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
    )
    service_ids = dict(bind.execute(sa.select(services.c.key, services.c.id)).all())
    signal_ids = dict(bind.execute(sa.select(signals.c.key, signals.c.id)).all())
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
    existing_mappings = set(
        bind.execute(
            sa.select(mappings.c.service_definition_id, mappings.c.signal_definition_id)
        ).all()
    )
    missing_mappings = []
    for _, service_key, _, _, _, signal_keys in SERVICES:
        service_id = service_ids.get(service_key)
        if service_id is None:
            continue
        for index, signal_key in enumerate(signal_keys):
            signal_id = signal_ids.get(signal_key)
            if signal_id is None or (service_id, signal_id) in existing_mappings:
                continue
            missing_mappings.append(
                {
                    "id": f"mapping_repair_{service_key}_{index + 1}",
                    "service_definition_id": service_id,
                    "signal_definition_id": signal_id,
                    "weight": 1.0,
                    "sort_order": index,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if missing_mappings:
        bind.execute(mappings.insert(), missing_mappings)


def downgrade() -> None:
    # This migration repairs required catalog data and must not remove rows that
    # may already be referenced by saved audience profiles.
    pass
