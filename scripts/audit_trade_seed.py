"""Audit a trade seed batch and verify deterministic profile matching."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys

from sqlalchemy import func, or_, select

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from canonical.normalization import nested_raw, normalize_business_name  # noqa: E402
from db.models import (  # noqa: E402
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SourceObservationModel,
)
from shared.utils import utcnow  # noqa: E402
from territories.matching import ProfileMatchService  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--niche", required=True)
    parser.add_argument("--city", default="Toronto")
    parser.add_argument("--center-lat", type=float, required=True)
    parser.add_argument("--center-lng", type=float, required=True)
    parser.add_argument("--radius-km", type=int, default=25)
    parser.add_argument("--match-limit", type=int, default=25)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        niche = session.scalar(select(NicheModel).where(NicheModel.slug == args.niche))
        if niche is None:
            raise SystemExit(f"niche not found: {args.niche}")
        rows = list(
            session.execute(
                select(BusinessModel, BusinessNicheMembershipModel)
                .join(
                    BusinessNicheMembershipModel,
                    BusinessNicheMembershipModel.business_id == BusinessModel.id,
                )
                .where(BusinessNicheMembershipModel.seed_batch_id == args.batch_id)
                .order_by(BusinessModel.display_name)
            )
        )
        businesses = [business for business, _ in rows]
        business_ids = [business.id for business in businesses]
        identity_mismatches = []
        for business, membership in rows:
            observation = (
                session.get(SourceObservationModel, membership.source_observation_id)
                if membership.source_observation_id
                else None
            )
            source_name = _source_company_name(observation.raw_payload if observation else None)
            if source_name and not _names_are_compatible(
                normalize_business_name(source_name),
                business.normalized_name,
            ):
                identity_mismatches.append(
                    {
                        "business": business.display_name,
                        "source_company": source_name,
                        "source_observation_id": membership.source_observation_id,
                    }
                )
        now = utcnow()
        fact_counts = dict(
            session.execute(
                select(BusinessFactModel.fact_key, func.count())
                .where(BusinessFactModel.business_id.in_(business_ids))
                .where(
                    or_(
                        BusinessFactModel.expires_at.is_(None),
                        BusinessFactModel.expires_at >= now,
                    )
                )
                .group_by(BusinessFactModel.fact_key)
            ).all()
        ) if business_ids else {}
        profile = SimpleNamespace(
            id=f"audit:{args.batch_id}",
            evidence_max_age_days=3650,
            trade_keys=[args.niche],
            customer_kind="residential",
            exclusion_keys=["closed", "chains", "franchises", "directories", "agencies"],
            signal_keys=[],
            latitude=args.center_lat,
            longitude=args.center_lng,
            radius_km=args.radius_km,
            city=args.city,
            market_key=args.city.lower(),
        )
        matches = ProfileMatchService(session).match(
            profile=profile,
            niche_ids=[niche.id],
            limit=args.match_limit,
        )
        report = {
            "batch_id": args.batch_id,
            "niche": args.niche,
            "business_count": len(businesses),
            "missing_phone": sum(not item.phone for item in businesses),
            "missing_coordinates": sum(
                item.latitude is None or item.longitude is None for item in businesses
            ),
            "residential_count": sum(
                item.customer_kind == "residential" for item in businesses
            ),
            "website_count": sum(bool(item.website_url) for item in businesses),
            "chain_count": sum(item.is_chain is True for item in businesses),
            "franchise_count": sum(item.is_franchise is True for item in businesses),
            "identity_mismatch_count": len(identity_mismatches),
            "identity_mismatch_sample": identity_mismatches[:10],
            "fact_counts": fact_counts,
            "matcher_count": len(matches),
            "matcher_sample": [item["title"] for item in matches[:10]],
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        if not matches:
            raise SystemExit("deterministic matcher returned zero rows")
        if report["missing_phone"] or report["missing_coordinates"]:
            raise SystemExit("seed batch is missing required matching fields")
        if identity_mismatches:
            raise SystemExit("seed batch contains canonical identity mismatches")
    finally:
        session_generator.close()


def _source_company_name(payload: dict | None) -> str | None:
    raw = nested_raw(payload)
    value = raw.get("company_name")
    if not value:
        display_name = raw.get("displayName")
        value = display_name.get("text") if isinstance(display_name, dict) else display_name
    cleaned = str(value or "").strip()
    return cleaned or None


def _names_are_compatible(first: str, second: str) -> bool:
    if first == second:
        return True
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    if min(len(first_tokens), len(second_tokens)) >= 2 and (
        first_tokens <= second_tokens or second_tokens <= first_tokens
    ):
        return True
    overlap = len(first_tokens & second_tokens)
    return overlap / max(len(first_tokens | second_tokens), 1) >= 0.6


if __name__ == "__main__":
    main()
