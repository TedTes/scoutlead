"""complete the scored business attribute catalog and backfill observed values

Revision ID: 20261101_0066
Revises: 20261101_0065
Create Date: 2026-11-01
"""

from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

from business_attributes.attribute_scoring import score_attribute
from canonical.normalization import external_id_from_raw, first_raw_text, nested_raw
from shared.utils import new_id


revision = "20261101_0066"
down_revision = "20261101_0065"
branch_labels = None
depends_on = None


# key, label, value type, category, collector, extractor, direction, status, config
ATTRIBUTES = (
    ("business_name", "Business name", "text", "identity", None, None, "none", "derived", {}),
    ("business_operational", "Business operational", "boolean", "identity", "google_places", "business_operational", "none", "active", {}),
    ("trade_category", "Trade/category", "text", "identity", None, None, "none", "derived", {}),
    ("provider_business_id", "Provider business ID", "text", "identity", None, None, "none", "derived", {}),
    ("address", "Address", "text", "location", None, None, "none", "derived", {}),
    ("city", "City", "text", "location", None, None, "none", "derived", {}),
    ("region", "Region", "text", "location", None, None, "none", "derived", {}),
    ("postal_code", "Postal code", "text", "location", None, None, "none", "derived", {}),
    ("latitude", "Latitude", "number", "location", None, None, "none", "derived", {}),
    ("longitude", "Longitude", "number", "location", None, None, "none", "derived", {}),
    ("phone", "Phone", "text", "contact", None, None, "none", "derived", {}),
    ("website_url", "Website URL", "text", "website", None, None, "none", "derived", {}),
    ("domain", "Domain", "text", "website", None, None, "none", "derived", {}),
    ("is_directory", "Directory", "boolean", "classification", None, None, "none", "derived", {}),
    ("is_chain", "Chain", "boolean", "classification", None, None, "none", "derived", {}),
    ("is_franchise", "Franchise", "boolean", "classification", None, None, "none", "derived", {}),
    ("website_status", "Website status", "text", "website", "website_http", "website_status", "missing_is_opportunity", "active", {}),
    ("website_ownership", "Website ownership", "text", "website", None, None, "none", "derived", {}),
    ("http_status", "HTTP status", "number", "website", "website_dom", "http_status", "higher_is_opportunity", "active", {"audience_max_score": 49.999}),
    ("uses_https", "HTTPS enabled", "boolean", "website", "website_dom", "uses_https", "false_is_opportunity", "active", {}),
    ("mobile_viewport_present", "Mobile viewport present", "boolean", "website", "website_dom", "mobile_viewport", "false_is_opportunity", "active", {}),
    ("website_quality_score", "Website quality score", "number", "website", "pagespeed_mobile", "pagespeed_quality_score", "lower_is_opportunity", "active", {"opportunity_threshold": 75}),
    ("performance_score", "Performance score", "number", "website", "pagespeed_mobile", "pagespeed_performance_score", "lower_is_opportunity", "active", {"opportunity_threshold": 70}),
    ("accessibility_score", "Accessibility score", "number", "website", "pagespeed_mobile", "pagespeed_accessibility_score", "lower_is_opportunity", "active", {"opportunity_threshold": 90}),
    ("best_practices_score", "Best-practices score", "number", "website", "pagespeed_mobile", "pagespeed_best_practices_score", "lower_is_opportunity", "active", {"opportunity_threshold": 90}),
    ("contact_form_present", "Contact form present", "boolean", "conversion", "website_dom", "contact_form", "false_is_opportunity", "active", {}),
    ("contact_page_url", "Contact page URL", "text", "conversion", "website_dom", "contact_page_url", "none", "active", {}),
    ("quote_or_booking_form_present", "Quote or booking form present", "boolean", "conversion", "website_dom", "quote_or_booking_form", "false_is_opportunity", "active", {}),
    ("booking_url", "Booking URL", "text", "conversion", "website_dom", "booking_url", "none", "active", {}),
    ("primary_cta_present", "Primary CTA present", "boolean", "conversion", "website_dom", "primary_cta", "false_is_opportunity", "active", {}),
    ("click_to_call_present", "Click-to-call present", "boolean", "conversion", "website_dom", "click_to_call", "false_is_opportunity", "active", {}),
    ("public_email_present", "Public email present", "boolean", "conversion", "website_dom", "public_email_present", "false_is_opportunity", "active", {}),
    ("public_phone_present", "Public phone present", "boolean", "conversion", "website_dom", "public_phone_present", "false_is_opportunity", "active", {}),
    ("google_rating", "Google rating", "number", "reputation", "google_places", "google_rating", "lower_is_opportunity", "active", {"opportunity_threshold": 4.3}),
    ("google_review_count", "Google review count", "number", "reputation", "google_places", "google_review_count", "lower_is_opportunity", "active", {"opportunity_threshold": 15}),
    ("review_recency_days", "Review recency", "number", "reputation", "google_places", "review_recency_days", "higher_is_opportunity", "active", {"opportunity_threshold": 180, "score_max": 365}),
    ("google_business_profile_present", "Google Business Profile present", "boolean", "local_seo", "google_places", "google_business_profile_present", "false_is_opportunity", "active", {}),
    ("local_business_schema_present", "Local business schema present", "boolean", "local_seo", "website_dom", "local_business_schema_present", "false_is_opportunity", "active", {}),
    ("service_area_content_present", "Service-area content present", "boolean", "local_seo", "website_dom", "service_area_pages", "false_is_opportunity", "active", {}),
    ("title_and_meta_present", "Title and meta description present", "boolean", "local_seo", "website_dom", "title_and_meta_present", "false_is_opportunity", "active", {}),
    ("verified_email", "Verified email", "text", "outreach", None, None, "none", "derived", {}),
    ("verified_phone", "Verified phone", "text", "outreach", None, None, "none", "derived", {}),
    ("contact_form_url", "Contact form URL", "text", "outreach", "website_dom", "contact_form_url", "none", "active", {}),
    ("preferred_contact_channel", "Preferred contact channel", "text", "outreach", None, None, "none", "derived", {}),
)

SERVICE_ATTRIBUTES = {
    "website_modernization": (
        "website_status",
        "http_status",
        "uses_https",
        "mobile_viewport_present",
        "website_quality_score",
        "performance_score",
        "accessibility_score",
        "best_practices_score",
    ),
    "lead_capture": (
        "contact_form_present",
        "primary_cta_present",
        "click_to_call_present",
        "public_email_present",
        "public_phone_present",
    ),
    "booking_payments": ("quote_or_booking_form_present",),
    "performance_accessibility": (
        "performance_score",
        "accessibility_score",
        "mobile_viewport_present",
    ),
    "local_visibility": (
        "google_business_profile_present",
        "local_business_schema_present",
        "service_area_content_present",
        "title_and_meta_present",
    ),
    "reputation_trust": (
        "google_rating",
        "google_review_count",
        "review_recency_days",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    definition_ids = _seed_catalog(bind)
    _replace_service_mappings(bind, definition_ids)
    _refresh_existing_audience_attributes(bind)
    _copy_alias_facts(bind, definition_ids)
    _backfill_core_attributes(bind, definition_ids)
    _backfill_validation_and_contact_attributes(bind, definition_ids)


def downgrade() -> None:
    # Canonical attribute facts may already be referenced by audience results.
    # A downgrade must not delete evidence or restore obsolete aliases.
    pass


def _seed_catalog(bind) -> dict[str, str]:
    definitions = _definitions_table()
    existing_rows = {
        row.key: row
        for row in bind.execute(
            sa.select(definitions.c.key, definitions.c.id, definitions.c.config)
        )
    }
    existing = {key: row.id for key, row in existing_rows.items()}
    now = datetime.now(timezone.utc)
    rows = []
    for key, label, value_type, category, collector, extractor, direction, status, config in ATTRIBUTES:
        if key in existing:
            # Promote catalog-only attributes once their canonical synchronizer
            # or deterministic collector is available.
            bind.execute(
                definitions.update()
                .where(definitions.c.key == key)
                .values(
                    label=label,
                    status=status,
                    collector_key=collector,
                    extractor_key=extractor,
                    opportunity_direction=direction,
                    config={
                        **(existing_rows[key].config or {}),
                        **config,
                        "auto_publish": status == "active",
                        "requires_validation": False,
                        "confidence": 95,
                    },
                )
            )
            continue
        definition_id = f"attribute_{key}"
        existing[key] = definition_id
        rows.append(
            {
                "id": definition_id,
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
                    **config,
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
    return {
        row.key: row.id
        for row in bind.execute(sa.select(definitions.c.key, definitions.c.id))
    }


def _replace_service_mappings(bind, definition_ids: dict[str, str]) -> None:
    services = sa.table(
        "service_definitions",
        sa.column("id", sa.String),
        sa.column("key", sa.String),
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
    service_ids = dict(bind.execute(sa.select(services.c.key, services.c.id)).all())
    now = datetime.now(timezone.utc)
    for service_key, attribute_keys in SERVICE_ATTRIBUTES.items():
        service_id = service_ids.get(service_key)
        if service_id is None:
            continue
        bind.execute(mappings.delete().where(mappings.c.service_definition_id == service_id))
        rows = [
            {
                "id": new_id("service_attribute"),
                "service_definition_id": service_id,
                "signal_definition_id": definition_ids[key],
                "weight": 1.0,
                "sort_order": index,
                "created_at": now,
                "updated_at": now,
            }
            for index, key in enumerate(attribute_keys)
            if key in definition_ids
        ]
        if rows:
            bind.execute(mappings.insert(), rows)


def _refresh_existing_audience_attributes(bind) -> None:
    territories = sa.table(
        "territories",
        sa.column("id", sa.String),
        sa.column("service_keys", sa.JSON),
        sa.column("signal_keys", sa.JSON),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    for row in bind.execute(
        sa.select(territories.c.id, territories.c.service_keys, territories.c.signal_keys)
    ).mappings():
        service_keys = list(row["service_keys"] or [])
        if not service_keys:
            continue
        mapped = [
            key
            for service_key in service_keys
            for key in SERVICE_ATTRIBUTES.get(service_key, ())
        ]
        # Service-backed audiences use the canonical current mapping. This
        # intentionally removes obsolete aliases that would otherwise count
        # the same observation twice during ranking.
        selected = list(dict.fromkeys(mapped))
        bind.execute(
            territories.update()
            .where(territories.c.id == row["id"])
            .values(signal_keys=selected, updated_at=now)
        )


def _copy_alias_facts(bind, definition_ids: dict[str, str]) -> None:
    aliases = {
        "mobile_performance_score": "performance_score",
        "service_area_pages_present": "service_area_content_present",
    }
    facts = _facts_table()
    existing = set(bind.execute(sa.select(facts.c.business_id, facts.c.fact_key)).all())
    rows = []
    now = datetime.now(timezone.utc)
    for old_key, new_key in aliases.items():
        for row in bind.execute(sa.select(facts).where(facts.c.fact_key == old_key)).mappings():
            if (row["business_id"], new_key) in existing:
                continue
            value = _fact_value(row)
            scored = score_attribute(new_key, value, config={"opportunity_threshold": 70})
            rows.append(
                {
                    **{key: row[key] for key in facts.c.keys() if key in row},
                    "id": new_id("business_fact"),
                    "fact_key": new_key,
                    "signal_definition_id": definition_ids.get(new_key),
                    "attribute_score": scored.score,
                    "score_version": scored.version,
                    "score_reason": scored.reason,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            existing.add((row["business_id"], new_key))
    if rows:
        bind.execute(facts.insert(), rows)


def _backfill_core_attributes(bind, definition_ids: dict[str, str]) -> None:
    businesses = sa.table(
        "businesses",
        sa.column("id", sa.String),
        sa.column("display_name", sa.String),
        sa.column("category_key", sa.String),
        sa.column("market_key", sa.String),
        sa.column("address", sa.Text),
        sa.column("latitude", sa.Float),
        sa.column("longitude", sa.Float),
        sa.column("phone", sa.String),
        sa.column("website_url", sa.String),
        sa.column("domain", sa.String),
        sa.column("is_directory", sa.Boolean),
        sa.column("is_chain", sa.Boolean),
        sa.column("is_franchise", sa.Boolean),
    )
    observations = sa.table(
        "source_observations",
        sa.column("id", sa.String),
        sa.column("business_id", sa.String),
        sa.column("source", sa.String),
        sa.column("raw_payload", sa.JSON),
        sa.column("observed_at", sa.DateTime(timezone=True)),
    )
    facts = _facts_table()
    ranked = (
        sa.select(
            observations,
            sa.func.row_number()
            .over(
                partition_by=observations.c.business_id,
                order_by=observations.c.observed_at.desc(),
            )
            .label("position"),
        )
        .subquery()
    )
    statement = (
        sa.select(
            businesses.c.id.label("canonical_business_id"),
            businesses.c.display_name,
            businesses.c.category_key,
            businesses.c.market_key,
            businesses.c.address,
            businesses.c.latitude,
            businesses.c.longitude,
            businesses.c.phone,
            businesses.c.website_url,
            businesses.c.domain,
            businesses.c.is_directory,
            businesses.c.is_chain,
            businesses.c.is_franchise,
            ranked.c.id.label("observation_id"),
            ranked.c.source,
            ranked.c.raw_payload,
            ranked.c.observed_at,
        )
        .join(ranked, ranked.c.business_id == businesses.c.id)
        .where(ranked.c.position == 1)
    )
    existing = set(bind.execute(sa.select(facts.c.business_id, facts.c.fact_key)).all())
    now = datetime.now(timezone.utc)
    rows = []
    for row in bind.execute(statement).mappings():
        raw = nested_raw(row["raw_payload"] or {})
        values = {
            "business_name": row["display_name"],
            "trade_category": row["category_key"],
            "provider_business_id": external_id_from_raw(raw),
            "address": row["address"],
            "city": first_raw_text(raw, ("city", "locality", "town")) or row["market_key"],
            "region": first_raw_text(raw, ("region", "province", "state", "administrative_area_level_1")),
            "postal_code": first_raw_text(raw, ("postal_code", "postcode", "zip", "zip_code")),
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "phone": row["phone"],
            "website_url": row["website_url"],
            "domain": row["domain"],
            "is_directory": row["is_directory"],
            "is_chain": row["is_chain"],
            "is_franchise": row["is_franchise"],
            "google_business_profile_present": (
                True if row["source"] in {"google_places", "google_places_seed"} else None
            ),
        }
        confidence = 95 if row["source"] in {"google_places", "google_places_seed", "openstreetmap"} else 85
        for key, value in values.items():
            if (
                value is None
                or value == ""
                or (row["canonical_business_id"], key) in existing
            ):
                continue
            score = score_attribute(key, value)
            value_type, value_text, value_number, value_boolean = _typed_value(value)
            rows.append(
                {
                    "id": new_id("business_fact"),
                    "business_id": row["canonical_business_id"],
                    "fact_key": key,
                    "signal_definition_id": definition_ids.get(key),
                    "value_type": value_type,
                    "value_text": value_text,
                    "value_number": value_number,
                    "value_boolean": value_boolean,
                    "confidence": confidence,
                    "attribute_score": score.score,
                    "score_version": score.version,
                    "score_reason": score.reason,
                    "resolution_state": "confirmed",
                    "supporting_claim_ids": [],
                    "quality_state": "staged",
                    "quality_policy_version": 1,
                    "observed_at": row["observed_at"],
                    "expires_at": row["observed_at"] + timedelta(days=365),
                    "source_observation_id": row["observation_id"],
                    "resolver_version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            existing.add((row["canonical_business_id"], key))
    for offset in range(0, len(rows), 1000):
        bind.execute(facts.insert(), rows[offset : offset + 1000])


def _backfill_validation_and_contact_attributes(
    bind,
    definition_ids: dict[str, str],
) -> None:
    facts = _facts_table()
    observations = sa.table(
        "source_observations",
        sa.column("id", sa.String),
        sa.column("business_id", sa.String),
        sa.column("observed_at", sa.DateTime(timezone=True)),
    )
    validations = sa.table(
        "validation_results",
        sa.column("id", sa.String),
        sa.column("business_id", sa.String),
        sa.column("source_observation_id", sa.String),
        sa.column("validation_type", sa.String),
        sa.column("status", sa.String),
        sa.column("confidence", sa.Integer),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    contacts = sa.table(
        "contacts",
        sa.column("id", sa.String),
        sa.column("business_id", sa.String),
        sa.column("email", sa.String),
        sa.column("phone", sa.String),
        sa.column("verification_status", sa.String),
        sa.column("verification_score", sa.Integer),
        sa.column("verification_checked_at", sa.DateTime(timezone=True)),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
    )
    latest_observation_rows = bind.execute(
        sa.select(
            observations.c.business_id,
            observations.c.id,
            observations.c.observed_at,
            sa.func.row_number()
            .over(
                partition_by=observations.c.business_id,
                order_by=observations.c.observed_at.desc(),
            )
            .label("position"),
        )
    ).mappings()
    latest_observations = {
        row["business_id"]: (row["id"], row["observed_at"])
        for row in latest_observation_rows
        if row["position"] == 1
    }
    existing = set(bind.execute(sa.select(facts.c.business_id, facts.c.fact_key)).all())
    now = datetime.now(timezone.utc)
    rows = []

    seen_ownership: set[str] = set()
    ownership_rows = bind.execute(
        sa.select(validations)
        .where(validations.c.validation_type == "website_ownership")
        .order_by(
            validations.c.business_id,
            validations.c.observed_at.desc(),
            validations.c.created_at.desc(),
        )
    ).mappings()
    for row in ownership_rows:
        business_id = row["business_id"]
        if business_id in seen_ownership or (business_id, "website_ownership") in existing:
            continue
        seen_ownership.add(business_id)
        source_observation_id = row["source_observation_id"]
        if source_observation_id is None:
            source_observation_id = (latest_observations.get(business_id) or (None, None))[0]
        if source_observation_id is None:
            continue
        rows.append(
            _derived_fact_row(
                business_id=business_id,
                key="website_ownership",
                value=row["status"],
                definition_id=definition_ids.get("website_ownership"),
                confidence=int(row["confidence"] or 0),
                observed_at=row["observed_at"],
                source_observation_id=source_observation_id,
                now=now,
            )
        )
        existing.add((business_id, "website_ownership"))

    verified_by_business: dict[str, dict[str, tuple[str, int, datetime]]] = {}
    for row in bind.execute(
        sa.select(contacts)
        .where(contacts.c.verification_status.in_(("valid", "verified", "passed")))
        .order_by(contacts.c.business_id, contacts.c.last_seen_at.desc())
    ).mappings():
        target = verified_by_business.setdefault(row["business_id"], {})
        confidence = int(row["verification_score"] or 90)
        observed_at = row["verification_checked_at"] or row["last_seen_at"]
        if row["email"] and "verified_email" not in target:
            target["verified_email"] = (row["email"], confidence, observed_at)

    contact_form_urls = {
        row["business_id"]: row["value_text"]
        for row in bind.execute(
            sa.select(facts.c.business_id, facts.c.value_text).where(
                facts.c.fact_key == "contact_form_url",
                facts.c.value_text.is_not(None),
            )
        ).mappings()
    }
    for business_id in set(verified_by_business) | set(contact_form_urls):
        observation = latest_observations.get(business_id)
        if observation is None:
            continue
        observation_id, fallback_observed_at = observation
        verified = verified_by_business.get(business_id, {})
        for key, (value, confidence, observed_at) in verified.items():
            if (business_id, key) in existing:
                continue
            rows.append(
                _derived_fact_row(
                    business_id=business_id,
                    key=key,
                    value=value,
                    definition_id=definition_ids.get(key),
                    confidence=confidence,
                    observed_at=observed_at or fallback_observed_at,
                    source_observation_id=observation_id,
                    now=now,
                )
            )
            existing.add((business_id, key))
        preferred = (
            "email"
            if "verified_email" in verified
            else "contact_form"
            if contact_form_urls.get(business_id)
            else None
        )
        if preferred and (business_id, "preferred_contact_channel") not in existing:
            rows.append(
                _derived_fact_row(
                    business_id=business_id,
                    key="preferred_contact_channel",
                    value=preferred,
                    definition_id=definition_ids.get("preferred_contact_channel"),
                    confidence=90,
                    observed_at=fallback_observed_at,
                    source_observation_id=observation_id,
                    now=now,
                )
            )
            existing.add((business_id, "preferred_contact_channel"))

    for offset in range(0, len(rows), 1000):
        bind.execute(facts.insert(), rows[offset : offset + 1000])


def _derived_fact_row(
    *,
    business_id: str,
    key: str,
    value,
    definition_id: str | None,
    confidence: int,
    observed_at,
    source_observation_id: str,
    now,
):
    score = score_attribute(key, value)
    value_type, value_text, value_number, value_boolean = _typed_value(value)
    return {
        "id": new_id("business_fact"),
        "business_id": business_id,
        "fact_key": key,
        "signal_definition_id": definition_id,
        "value_type": value_type,
        "value_text": value_text,
        "value_number": value_number,
        "value_boolean": value_boolean,
        "confidence": confidence,
        "attribute_score": score.score,
        "score_version": score.version,
        "score_reason": score.reason,
        "resolution_state": "confirmed",
        "supporting_claim_ids": [],
        "quality_state": "staged",
        "quality_policy_version": 1,
        "observed_at": observed_at,
        "expires_at": observed_at + timedelta(days=365),
        "source_observation_id": source_observation_id,
        "resolver_version": 1,
        "created_at": now,
        "updated_at": now,
    }


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


def _facts_table():
    return sa.table(
        "business_facts",
        sa.column("id", sa.String),
        sa.column("business_id", sa.String),
        sa.column("fact_key", sa.String),
        sa.column("signal_definition_id", sa.String),
        sa.column("value_type", sa.String),
        sa.column("value_text", sa.Text),
        sa.column("value_number", sa.Float),
        sa.column("value_boolean", sa.Boolean),
        sa.column("confidence", sa.Integer),
        sa.column("attribute_score", sa.Float),
        sa.column("score_version", sa.Integer),
        sa.column("score_reason", sa.Text),
        sa.column("resolution_state", sa.String),
        sa.column("supporting_claim_ids", sa.JSON),
        sa.column("quality_state", sa.String),
        sa.column("quality_policy_version", sa.Integer),
        sa.column("observed_at", sa.DateTime(timezone=True)),
        sa.column("expires_at", sa.DateTime(timezone=True)),
        sa.column("source_observation_id", sa.String),
        sa.column("resolver_version", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _fact_value(row):
    if row["value_type"] == "boolean":
        return row["value_boolean"]
    if row["value_type"] == "number":
        return row["value_number"]
    return row["value_text"]


def _typed_value(value):
    if isinstance(value, bool):
        return "boolean", None, None, value
    if isinstance(value, (int, float)):
        return "number", None, float(value), None
    return "text", str(value), None, None
