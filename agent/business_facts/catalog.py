from __future__ import annotations


TRACKED_ATTRIBUTE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "identity",
        "Core identity and targeting",
        (
            "business_name", "business_operational", "trade_category",
            "provider_business_id", "address", "city", "region", "postal_code",
            "latitude", "longitude", "phone", "website_url", "domain",
            "is_directory", "is_chain", "is_franchise",
        ),
    ),
    (
        "website",
        "Website",
        (
            "website_status", "website_ownership", "http_status", "uses_https",
            "mobile_viewport_present", "website_quality_score", "performance_score",
            "accessibility_score", "best_practices_score",
        ),
    ),
    (
        "lead_capture",
        "Lead capture",
        (
            "contact_form_present", "contact_page_url", "quote_or_booking_form_present",
            "booking_url", "primary_cta_present", "click_to_call_present",
            "public_email_present", "public_phone_present",
        ),
    ),
    (
        "reputation",
        "Reputation",
        ("google_rating", "google_review_count", "review_recency_days"),
    ),
    (
        "local_visibility",
        "Local visibility attributes",
        (
            "google_business_profile_present", "local_business_schema_present",
            "service_area_content_present", "title_and_meta_present",
        ),
    ),
    (
        "outreach",
        "Outreach readiness",
        ("verified_email", "verified_phone", "contact_form_url", "preferred_contact_channel"),
    ),
)

TRACKED_ATTRIBUTE_KEYS = tuple(
    key for _, _, keys in TRACKED_ATTRIBUTE_GROUPS for key in keys
)

ATTRIBUTE_GROUP_BY_KEY = {
    key: {"key": group_key, "label": group_label, "sort_order": group_order}
    for group_order, (group_key, group_label, keys) in enumerate(TRACKED_ATTRIBUTE_GROUPS)
    for key in keys
}

ATTRIBUTE_SORT_ORDER = {
    key: attribute_order
    for _, _, keys in TRACKED_ATTRIBUTE_GROUPS
    for attribute_order, key in enumerate(keys)
}
