#!/usr/bin/env python3
"""Audit or repair validation and derived facts for existing business inventory.

The default mode is read-only. ``--apply`` records validation outcomes, updates
source-item workflow states, and reconciles facts using current ownership rules.
"""

from __future__ import annotations

import argparse
from collections import Counter
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
from business_validation.policy import publication_decision  # noqa: E402
from business_validation.validation import BusinessValidationService  # noqa: E402
from db.models import (  # noqa: E402
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    SourceItemModel,
    SourceObservationModel,
)
from db.session import Database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database = Database(get_settings().database_url)
    with database.session_factory() as session:
        statement = (
            select(BusinessNicheMembershipModel, BusinessModel, NicheModel)
            .join(BusinessModel, BusinessModel.id == BusinessNicheMembershipModel.business_id)
            .join(NicheModel, NicheModel.id == BusinessNicheMembershipModel.niche_id)
            .order_by(BusinessNicheMembershipModel.last_seen_at.desc())
        )
        if args.niche:
            statement = statement.where(NicheModel.slug == args.niche)
        if args.market:
            statement = statement.where(
                BusinessNicheMembershipModel.market_key.ilike(f"%{args.market}%")
            )
        rows = list(session.execute(statement.limit(args.limit)).all())
        business_ids = {business.id for _, business, _ in rows}
        segments_by_scope = {
            (segment.niche_id, segment.market_key): segment
            for segment in session.scalars(select(BusinessIndexSegmentModel))
        }
        observations = list(
            session.scalars(
                select(SourceObservationModel)
                .where(SourceObservationModel.business_id.in_(business_ids))
                .order_by(SourceObservationModel.observed_at.desc())
            )
        )
        observations_by_id = {observation.id: observation for observation in observations}
        latest_observation_by_business = {}
        for observation in observations:
            latest_observation_by_business.setdefault(observation.business_id, observation)
        source_items = list(
            session.scalars(
                select(SourceItemModel)
                .where(SourceItemModel.business_id.in_(business_ids))
                .order_by(SourceItemModel.fetched_at.desc())
            )
        )
        source_items_by_scope = {}
        for source_item in source_items:
            source_items_by_scope.setdefault(
                (source_item.business_id, source_item.segment_id), source_item
            )
        counts: Counter[str] = Counter()
        issues: Counter[str] = Counter()
        validation_counts: Counter[str] = Counter()
        by_niche: dict[str, Counter[str]] = {}
        by_source: dict[str, Counter[str]] = {}
        details: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        for membership, business, niche in rows:
            key = (business.id, niche.id, membership.market_key)
            if key in seen:
                continue
            seen.add(key)
            segment = segments_by_scope.get((niche.id, membership.market_key))
            if segment is None:
                issues["missing_segment"] += 1
                segment = SimpleNamespace(
                    id=None,
                    niche_id=niche.id,
                    niche=niche,
                    market_key=membership.market_key,
                    market_label=membership.market_key,
                )

            source_item = source_items_by_scope.get((business.id, segment.id))
            observation = (
                observations_by_id.get(membership.source_observation_id)
                if membership.source_observation_id
                else None
            )
            if observation is None:
                issues["missing_membership_observation"] += 1
                observation = latest_observation_by_business.get(business.id)
            validator = BusinessValidationService(session)
            if source_item is not None:
                results = (
                    validator.validate(
                        business=business,
                        source_item=source_item,
                        segment=segment,
                    )
                    if args.apply
                    else validator.evaluate(
                        business=business,
                        source_item=source_item,
                        segment=segment,
                    )
                )
            elif observation is not None:
                results = (
                    validator.validate_observation(
                        business=business,
                        observation=observation,
                        segment=segment,
                    )
                    if args.apply
                    else validator.evaluate_observation(
                        business=business,
                        observation=observation,
                        segment=segment,
                    )
                )
            else:
                issues["missing_source"] += 1
                details.append(_detail(business, niche, membership, "missing_source"))
                continue

            decision = publication_decision(results)
            counts[decision.status] += 1
            source = (
                observation.source
                if observation is not None
                else source_item.provider_id
                if source_item is not None
                else "unknown"
            )
            by_niche.setdefault(niche.slug, Counter())[decision.status] += 1
            by_source.setdefault(source, Counter())[decision.status] += 1
            for result in results:
                validation_counts[f"{result.validation_type}:{result.status}"] += 1
            if args.apply:
                if source_item is not None:
                    source_item.state = {
                        "publishable": "eligible",
                        "needs_review": "needs_review",
                        "rejected": "rejected",
                    }[decision.status]
                reconcile_business_facts(session, business.id)
                session.commit()
            details.append(
                {
                    **_detail(business, niche, membership, decision.status),
                    "reasons": list(decision.reasons),
                    "missing_validations": list(decision.missing),
                    "validations": {
                        result.validation_type: {
                            "status": result.status,
                            "confidence": result.confidence,
                            "reason": result.reason,
                            "evidence": result.evidence,
                        }
                        for result in results
                    },
                }
            )

        summary = {
            "dry_run": not args.apply,
            "evaluated": sum(counts.values()),
            "counts": dict(sorted(counts.items())),
            "structural_issues": dict(sorted(issues.items())),
            "validation_dimensions": dict(sorted(validation_counts.items())),
            "by_niche": {
                key: dict(sorted(value.items())) for key, value in sorted(by_niche.items())
            },
            "by_source": {
                key: dict(sorted(value.items())) for key, value in sorted(by_source.items())
            },
            "details": details if args.details else [],
        }
        rendered = json.dumps(summary, indent=2, sort_keys=True)
        if args.output:
            Path(args.output).write_text(f"{rendered}\n", encoding="utf-8")
        else:
            print(rendered)
    return 0


def _detail(business, niche, membership, status: str) -> dict:
    return {
        "business_id": business.id,
        "business": business.display_name,
        "niche": niche.slug,
        "market": membership.market_key,
        "status": status,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--niche")
    parser.add_argument("--market")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--output")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
