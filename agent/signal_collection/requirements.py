from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_

from shared.utils import utcnow


# The standing sweep is deliberately limited to the two user-facing website
# opportunities. One website-status inspection still preserves its full raw
# DOM evidence, while PageSpeed preserves all Lighthouse categories; granular
# attributes can be derived or explicitly recollected without multiplying the
# external request backlog.
STANDING_WEBSITE_ATTRIBUTE_KEYS = frozenset(
    {
        "website_status",
        "website_quality_score",
    }
)


def fact_requires_collection(fact, *, now: datetime | None = None):
    """One shared SQL predicate for missing, unresolved, or stale evidence."""

    current_time = now or utcnow()
    return or_(
        fact.id.is_(None),
        fact.quality_state == "staged",
        fact.resolution_state != "confirmed",
        fact.expires_at.is_(None),
        fact.expires_at <= current_time,
    )
