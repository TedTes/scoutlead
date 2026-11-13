from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_

from shared.utils import utcnow


# The user selects one website-upgrade opportunity, but that decision is backed
# by several independently auditable attributes.  Website DOM collection reuses
# one recent observation for every definition, so keeping the component keys in
# the standing sweep does not require a fresh crawl per attribute.
STANDING_WEBSITE_ATTRIBUTE_KEYS = frozenset(
    {
        "website_status",
        "website_quality_score",
        "mobile_viewport_present",
        "primary_cta_present",
        "click_to_call_present",
    }
)


def fact_requires_collection(fact, *, now: datetime | None = None):
    """One shared SQL predicate for missing or stale evidence."""

    current_time = now or utcnow()
    return or_(
        fact.id.is_(None),
        fact.expires_at.is_(None),
        fact.expires_at <= current_time,
    )
