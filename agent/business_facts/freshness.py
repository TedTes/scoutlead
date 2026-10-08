from __future__ import annotations

from datetime import datetime, timedelta


FACT_TTL_DAYS = {
    "website_status": 30,
    "quote_or_booking_form_present": 30,
    "contact_form_present": 30,
    "google_rating": 14,
    "google_review_count": 14,
    "business_operational": 14,
}


def fact_expires_at(fact_key: str, observed_at: datetime) -> datetime:
    return observed_at + timedelta(days=FACT_TTL_DAYS.get(fact_key, 30))


def fact_is_current(*, expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None and now.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=now.tzinfo)
    return expires_at >= now
