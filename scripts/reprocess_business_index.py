#!/usr/bin/env python3
"""Rebuild claims, validations, fact quality, and publication decisions.

Dry run by default. Pass --apply after reviewing the reported scope.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from business_facts.service import reconcile_business_facts  # noqa: E402
from db.models import (  # noqa: E402
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SourceObservationModel,
)
from db.session import Database  # noqa: E402
from publication.policy import PublicationPolicyService  # noqa: E402
from publication.validation import BusinessValidationService  # noqa: E402
from seeding.batches import active_membership_condition  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database = Database(get_settings().database_url)
    with database.session_factory() as session:
        memberships = _memberships(
            session,
            niche_slug=args.niche,
            market_key=args.market,
            limit=args.limit,
        )
        business_ids = sorted({membership.business_id for membership, _ in memberships})
        observations = {
            business_id: session.scalar(
                select(SourceObservationModel)
                .where(SourceObservationModel.business_id == business_id)
                .order_by(SourceObservationModel.observed_at.desc())
                .limit(1)
            )
            for business_id in business_ids
        }
        summary = {
            "dry_run": not args.apply,
            "businesses": len(business_ids),
            "scopes": len(memberships),
            "without_observation": sum(
                observation is None for observation in observations.values()
            ),
            "publication_states": {},
        }
        if not args.apply:
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0

        for business_id in business_ids:
            reconcile_business_facts(session, business_id)
        session.commit()

        publication_states: dict[str, int] = {}
        validator = BusinessValidationService(session)
        policy = PublicationPolicyService(session)
        for membership, niche in memberships:
            business = session.get(BusinessModel, membership.business_id)
            observation = observations.get(membership.business_id)
            if business is None or observation is None:
                continue
            scope = SimpleNamespace(
                niche_id=niche.id,
                niche=niche,
                market_key=membership.market_key,
                market_label=membership.market_key,
            )
            validator.validate_observation(
                business=business,
                observation=observation,
                segment=scope,
            )
            publication = policy.evaluate(
                business_id=business.id,
                niche_id=niche.id,
                market_key=membership.market_key,
                source=observation.source,
            )
            publication_states[publication.status] = (
                publication_states.get(publication.status, 0) + 1
            )
        summary["publication_states"] = publication_states
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _memberships(session, *, niche_slug, market_key, limit):
    statement = (
        select(BusinessNicheMembershipModel, NicheModel)
        .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
        .where(active_membership_condition())
        .order_by(
            NicheModel.slug,
            BusinessNicheMembershipModel.market_key,
            BusinessNicheMembershipModel.business_id,
        )
    )
    if niche_slug:
        statement = statement.where(NicheModel.slug == niche_slug)
    if market_key:
        statement = statement.where(
            BusinessNicheMembershipModel.market_key == market_key.strip().lower()
        )
    if limit:
        statement = statement.limit(max(1, limit))
    return list(session.execute(statement).all())


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--niche", help="Restrict to one niche slug.")
    parser.add_argument("--market", help="Restrict to one normalized market key.")
    parser.add_argument("--limit", type=int, help="Limit membership scopes for a canary run.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the reprocessed data. The default is a read-only dry run.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
