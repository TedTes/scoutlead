"""Audit and remove cross-trade memberships created from lexical discovery.

The command is a dry run unless ``--apply`` is passed. Seed imports and explicit
trade associations are never removed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from db.models import (  # noqa: E402
    BusinessModel,
    BusinessNicheMembershipModel,
    LeadModel,
    NicheModel,
    TerritoryModel,
)


TRADE_TERMS = {
    "home_service_painting": {"paint", "painter", "painting"},
    "home_service_hvac": {
        "air conditioning",
        "cooling",
        "furnace",
        "heating",
        "hvac",
    },
    "home_service_roofing": {"roof", "roofer", "roofing"},
    "home_service_plumbing": {"plumber", "plumbing"},
    "home_service_electrical": {"electric", "electrical", "electrician"},
}


@dataclass(frozen=True)
class InvalidMembership:
    membership_id: str
    business_id: str
    business_name: str
    niche_id: str
    niche_slug: str
    evidence_queries: tuple[str, ...]


def find_invalid_memberships(session: Session) -> list[InvalidMembership]:
    rows = session.execute(
        select(BusinessNicheMembershipModel, BusinessModel, NicheModel)
        .join(BusinessModel, BusinessModel.id == BusinessNicheMembershipModel.business_id)
        .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
        .where(NicheModel.slug.in_(TRADE_TERMS))
        .order_by(NicheModel.slug, BusinessModel.display_name)
    ).all()
    invalid: list[InvalidMembership] = []
    for membership, business, niche in rows:
        if membership.seed_batch_id is not None:
            continue
        evidence = membership.evidence if isinstance(membership.evidence, list) else []
        if not evidence or any(_is_explicit(item) for item in evidence):
            continue
        lexical = [item for item in evidence if _is_lexical(item)]
        if not lexical:
            continue
        queries = tuple(
            str(item.get("query") or "").strip()
            for item in lexical
            if str(item.get("query") or "").strip()
        )
        if any(_mentions_trade(query, niche.slug) for query in queries):
            continue
        invalid.append(
            InvalidMembership(
                membership_id=membership.id,
                business_id=business.id,
                business_name=business.display_name,
                niche_id=niche.id,
                niche_slug=niche.slug,
                evidence_queries=queries,
            )
        )
    return invalid


def apply_cleanup(session: Session, invalid: list[InvalidMembership]) -> dict[str, int]:
    invalid_ids = {item.membership_id for item in invalid}
    invalid_pairs = {(item.business_id, item.niche_id) for item in invalid}
    memberships = list(
        session.scalars(
            select(BusinessNicheMembershipModel).where(
                BusinessNicheMembershipModel.id.in_(invalid_ids)
            )
        )
    ) if invalid_ids else []
    for membership in memberships:
        session.delete(membership)

    leads_changed = 0
    if invalid_pairs:
        leads = session.execute(
            select(LeadModel, TerritoryModel)
            .join(TerritoryModel, TerritoryModel.id == LeadModel.territory_id)
            .where(LeadModel.business_id.is_not(None))
            .where(LeadModel.review_status == "unreviewed")
        ).all()
        for lead, profile in leads:
            if (lead.business_id, profile.niche_id) not in invalid_pairs:
                continue
            lead.status = "disqualified"
            lead.review_status = "not_fit"
            lead.review_note = "Removed from this audience after invalid cross-trade membership cleanup."
            qualification = dict(lead.qualification or {})
            qualification.update(
                {
                    "qualified": False,
                    "fit_status": "not_fit",
                    "rationale": "The stored trade membership was not supported by its source evidence.",
                    "recommended_next_step": "Do not use this lead for this audience.",
                }
            )
            lead.qualification = qualification
            leads_changed += 1

    session.commit()
    return {"memberships_removed": len(memberships), "leads_disqualified": leads_changed}


def _is_explicit(evidence: object) -> bool:
    return isinstance(evidence, dict) and (
        evidence.get("type") == "seed_import"
        or evidence.get("resolution_type") == "explicit"
    )


def _is_lexical(evidence: object) -> bool:
    return isinstance(evidence, dict) and evidence.get("resolution_type") == "lexical"


def _mentions_trade(query: str, niche_slug: str) -> bool:
    normalized = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    return any(term in normalized for term in TRADE_TERMS[niche_slug])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit the reported cleanup.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        invalid = find_invalid_memberships(session)
        counts: dict[str, int] = {}
        for item in invalid:
            counts[item.niche_slug] = counts.get(item.niche_slug, 0) + 1
        report = {
            "mode": "apply" if args.apply else "dry_run",
            "invalid_memberships": len(invalid),
            "by_niche": counts,
            "sample": [
                {
                    "business": item.business_name,
                    "niche": item.niche_slug,
                    "queries": list(item.evidence_queries),
                }
                for item in invalid[:20]
            ],
        }
        if args.apply:
            report.update(apply_cleanup(session, invalid))
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        session_generator.close()


if __name__ == "__main__":
    main()
