"""Audit canonical business-pool readiness.

Examples:
    python scripts/audit_business_pool.py
    python scripts/audit_business_pool.py --category painting --market toronto
    python scripts/audit_business_pool.py --category painting --market toronto --json
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.models import BusinessModel, ContactModel, LeadModel, SourceObservationModel  # noqa: E402
from db.session import Database  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    database = Database(settings.database_url)
    session = next(database.session())
    try:
        audit = build_audit(
            session,
            category=args.category,
            market=args.market,
            source=args.source,
            stale_days=args.stale_days,
            duplicate_limit=args.duplicate_limit,
        )
    finally:
        session.close()

    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True, default=str))
        return
    print_audit(audit)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit canonical ScoutLead business-pool quality.")
    parser.add_argument("--category", help="Case-insensitive category/semantic text filter.")
    parser.add_argument("--market", help="Case-insensitive market/geography/address filter.")
    parser.add_argument("--source", help="Case-insensitive source-observation filter.")
    parser.add_argument("--stale-days", type=int, default=90, help="Rows older than this are stale.")
    parser.add_argument("--duplicate-limit", type=int, default=10, help="Duplicate groups to display.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def build_audit(
    session: Session,
    *,
    category: str | None = None,
    market: str | None = None,
    source: str | None = None,
    stale_days: int = 90,
    duplicate_limit: int = 10,
) -> dict[str, Any]:
    businesses = list(
        session.scalars(
            _business_statement(category=category, market=market, source=source).order_by(
                BusinessModel.display_name
            )
        )
    )
    business_ids = [business.id for business in businesses]
    contacts = _contacts_for_businesses(session, business_ids)
    observations = _observations_for_businesses(session, business_ids)
    leads = _leads_for_businesses(session, business_ids)
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(days=max(1, stale_days))

    contact_business_ids = {contact.business_id for contact in contacts}
    email_business_ids = {contact.business_id for contact in contacts if contact.email}
    valid_email_business_ids = {
        contact.business_id
        for contact in contacts
        if contact.email and contact.verification_status == "valid"
    }
    quote_signal_business_ids = {
        business.id
        for business in businesses
        if _has_quote_signal(business, observations_by_business=observations)
    }
    stale_business_ids = {
        business.id
        for business in businesses
        if _aware_datetime(business.last_seen_at) < stale_before
    }

    return {
        "filters": {
            "category": category or "",
            "market": market or "",
            "source": source or "",
            "stale_days": stale_days,
        },
        "businesses": {
            "total": len(businesses),
            "with_website": _count_if(businesses, lambda row: bool(row.website_url or row.domain)),
            "with_phone": _count_if(businesses, lambda row: bool(row.phone)),
            "with_address": _count_if(businesses, lambda row: bool(row.address or row.geography)),
            "with_semantic_text": _count_if(businesses, lambda row: bool(row.semantic_text)),
            "with_embedding": _count_if(businesses, lambda row: bool(row.embedding)),
            "with_quote_or_estimate_signal": len(quote_signal_business_ids),
            "stale": len(stale_business_ids),
        },
        "contacts": {
            "total": len(contacts),
            "businesses_with_any_contact": len(contact_business_ids),
            "businesses_with_email": len(email_business_ids),
            "businesses_with_valid_email": len(valid_email_business_ids),
            "businesses_with_phone_or_email": len(
                {
                    contact.business_id
                    for contact in contacts
                    if contact.email or contact.phone
                }
                | {business.id for business in businesses if business.phone}
            ),
            "verification_statuses": dict(Counter(contact.verification_status for contact in contacts)),
        },
        "sources": {
            "observations": len(observations),
            "by_source": _top_counts(observations, lambda row: row.source),
            "by_seed_batch": _top_counts(
                observations,
                lambda row: str((row.raw_payload or {}).get("seed_batch_id") or ""),
            ),
        },
        "taxonomy": {
            "by_category": _top_counts(businesses, lambda row: row.category_key or ""),
            "by_market": _top_counts(businesses, lambda row: row.market_key or ""),
        },
        "history": {
            "businesses_in_leads": len({lead.business_id for lead in leads if lead.business_id}),
            "shortlisted_businesses": len(
                {lead.business_id for lead in leads if lead.business_id and lead.shortlisted_at}
            ),
            "contacted_businesses": len(
                {lead.business_id for lead in leads if lead.business_id and lead.last_contacted_at}
            ),
            "passed_or_not_fit_businesses": len(
                {
                    lead.business_id
                    for lead in leads
                    if lead.business_id and lead.review_status in {"not_fit"}
                }
            ),
        },
        "duplicate_candidates": {
            "by_domain": _duplicate_groups(
                businesses,
                lambda row: row.domain or "",
                duplicate_limit,
            ),
            "by_phone": _duplicate_groups(
                businesses,
                lambda row: row.phone or "",
                duplicate_limit,
            ),
            "by_name_market": _duplicate_groups(
                businesses,
                lambda row: f"{row.normalized_name}|{row.market_key or row.geography or ''}",
                duplicate_limit,
            ),
        },
    }


def print_audit(audit: dict[str, Any]) -> None:
    businesses = audit["businesses"]
    contacts = audit["contacts"]
    sources = audit["sources"]
    taxonomy = audit["taxonomy"]
    history = audit["history"]
    total = businesses["total"]

    print("Business pool audit")
    print(f"Filters: {_filter_line(audit['filters'])}")
    print()
    print(f"Businesses: {total}")
    _print_metric("with website", businesses["with_website"], total)
    _print_metric("with phone", businesses["with_phone"], total)
    _print_metric("with address/geography", businesses["with_address"], total)
    _print_metric("with semantic text", businesses["with_semantic_text"], total)
    _print_metric("with embedding", businesses["with_embedding"], total)
    _print_metric("with quote/estimate signal", businesses["with_quote_or_estimate_signal"], total)
    _print_metric(f"stale > {audit['filters']['stale_days']} days", businesses["stale"], total)
    print()
    print(f"Contacts: {contacts['total']}")
    _print_metric("businesses with any contact", contacts["businesses_with_any_contact"], total)
    _print_metric("businesses with email", contacts["businesses_with_email"], total)
    _print_metric("businesses with valid email", contacts["businesses_with_valid_email"], total)
    _print_metric("businesses with phone or email", contacts["businesses_with_phone_or_email"], total)
    _print_counts("verification statuses", contacts["verification_statuses"])
    print()
    print(f"Source observations: {sources['observations']}")
    _print_counts("sources", sources["by_source"])
    _print_counts("seed batches", sources["by_seed_batch"])
    print()
    _print_counts("categories", taxonomy["by_category"])
    _print_counts("markets", taxonomy["by_market"])
    print()
    print("History")
    _print_metric("businesses promoted into leads", history["businesses_in_leads"], total)
    _print_metric("shortlisted businesses", history["shortlisted_businesses"], total)
    _print_metric("contacted businesses", history["contacted_businesses"], total)
    _print_metric("passed/not-fit businesses", history["passed_or_not_fit_businesses"], total)
    print()
    print("Duplicate candidates")
    _print_duplicate_summary("domain", audit["duplicate_candidates"]["by_domain"])
    _print_duplicate_summary("phone", audit["duplicate_candidates"]["by_phone"])
    _print_duplicate_summary("name + market", audit["duplicate_candidates"]["by_name_market"])


def _business_statement(*, category: str | None, market: str | None, source: str | None):
    statement = select(BusinessModel)
    if category:
        pattern = _like_pattern(category)
        statement = statement.where(
            or_(
                func.lower(BusinessModel.category_key).like(pattern),
                func.lower(BusinessModel.semantic_text).like(pattern),
                func.lower(BusinessModel.display_name).like(pattern),
            )
        )
    if market:
        pattern = _like_pattern(market)
        statement = statement.where(
            or_(
                func.lower(BusinessModel.market_key).like(pattern),
                func.lower(BusinessModel.geography).like(pattern),
                func.lower(BusinessModel.address).like(pattern),
            )
        )
    if source:
        pattern = _like_pattern(source)
        source_business_ids = select(SourceObservationModel.business_id).where(
            func.lower(SourceObservationModel.source).like(pattern)
        )
        statement = statement.where(BusinessModel.id.in_(source_business_ids))
    return statement


def _contacts_for_businesses(session: Session, business_ids: list[str]) -> list[ContactModel]:
    if not business_ids:
        return []
    return list(session.scalars(select(ContactModel).where(ContactModel.business_id.in_(business_ids))))


def _observations_for_businesses(
    session: Session, business_ids: list[str]
) -> list[SourceObservationModel]:
    if not business_ids:
        return []
    return list(
        session.scalars(select(SourceObservationModel).where(SourceObservationModel.business_id.in_(business_ids)))
    )


def _leads_for_businesses(session: Session, business_ids: list[str]) -> list[LeadModel]:
    if not business_ids:
        return []
    return list(session.scalars(select(LeadModel).where(LeadModel.business_id.in_(business_ids))))


def _top_counts(rows: list[Any], key_fn: Callable[[Any], str], limit: int = 12) -> dict[str, int]:
    counts = Counter(_clean_key(key_fn(row)) for row in rows)
    counts.pop("", None)
    return dict(counts.most_common(limit))


def _duplicate_groups(
    businesses: list[BusinessModel],
    key_fn: Callable[[BusinessModel], str],
    limit: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[BusinessModel]] = defaultdict(list)
    for business in businesses:
        key = _clean_key(key_fn(business))
        if key:
            grouped[key].append(business)
    duplicates = [
        {
            "key": key,
            "count": len(rows),
            "examples": [row.display_name for row in rows[:3]],
        }
        for key, rows in grouped.items()
        if len(rows) > 1
    ]
    duplicates.sort(key=lambda row: (-row["count"], row["key"]))
    return duplicates[: max(0, limit)]


def _has_quote_signal(
    business: BusinessModel,
    *,
    observations_by_business: list[SourceObservationModel],
) -> bool:
    text_parts = [business.semantic_text or "", business.display_name or ""]
    for observation in observations_by_business:
        if observation.business_id != business.id:
            continue
        raw_payload = observation.raw_payload or {}
        if observation.source == "company_website_seed":
            website_enrichment = raw_payload.get("website_enrichment")
            if isinstance(website_enrichment, dict) and (
                website_enrichment.get("has_quote_form") or website_enrichment.get("quote_signals")
            ):
                return True
            continue
        text_parts.extend(_raw_quote_signal_text(raw_payload))
    text = " ".join(text_parts).lower()
    return any(term in text for term in ("quote", "estimate", "request a quote", "free quote"))


def _raw_quote_signal_text(raw_payload: dict[str, Any]) -> list[str]:
    text_parts: list[str] = []
    for key in ("description", "query", "search_query"):
        value = raw_payload.get(key)
        if isinstance(value, str):
            text_parts.append(value)
    signals = raw_payload.get("signals")
    if isinstance(signals, list):
        text_parts.extend(signal for signal in signals if isinstance(signal, str))
    return text_parts


def _filter_line(filters: dict[str, Any]) -> str:
    parts = [
        f"category contains {filters['category']!r}" if filters.get("category") else "",
        f"market contains {filters['market']!r}" if filters.get("market") else "",
        f"source contains {filters['source']!r}" if filters.get("source") else "",
    ]
    return ", ".join(part for part in parts if part) or "none"


def _print_metric(label: str, value: int, total: int) -> None:
    print(f"  {label}: {value} ({_percent(value, total)})")


def _print_counts(label: str, counts: dict[str, int]) -> None:
    if not counts:
        print(f"  {label}: none")
        return
    print(f"  {label}:")
    for key, count in counts.items():
        print(f"    {key}: {count}")


def _print_duplicate_summary(label: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        print(f"  {label}: none")
        return
    print(f"  {label}: {len(rows)} group(s)")
    for row in rows:
        examples = "; ".join(row["examples"])
        print(f"    {row['key']}: {row['count']} ({examples})")


def _count_if(rows: list[Any], predicate: Callable[[Any], bool]) -> int:
    return sum(1 for row in rows if predicate(row))


def _percent(value: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    return f"{round((value / total) * 100)}%"


def _like_pattern(value: str) -> str:
    return f"%{value.strip().lower()}%"


def _clean_key(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
