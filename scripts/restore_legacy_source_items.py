#!/usr/bin/env python3
"""Restore pre-source-item observations into the durable business-index pipeline.

The command is read-only by default. Pass ``--apply`` to create missing Toronto
segments, materialize deduplicated source items, and queue one validation job per
legacy business. Validation runs through the normal opportunity-audit stage.
Existing canonical businesses and observations are preserved.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.models import (  # noqa: E402
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    NicheModel,
    ProductModel,
    SourceItemDecisionModel,
    SourceItemModel,
    SourceObservationModel,
)
from db.session import Database  # noqa: E402
from job_queue.repository import QueueRepository  # noqa: E402
from job_queue.schemas import JobType  # noqa: E402
from niches.catalog import NICHE_BY_SLUG  # noqa: E402
from shared.utils import new_id, utcnow  # noqa: E402
from source_items.repository import source_item_content_hash  # noqa: E402
from source_items.schemas import SourceItemCreate  # noqa: E402


MARKER = "legacy_source_observation_restore_v1"
MARKET_KEY = "toronto"
MARKET_LABEL = "Toronto"
SOURCE_PRIORITY = {
    "google_places": 0,
    "google_places_seed": 1,
    "company_website_seed": 2,
    "openstreetmap_seed": 3,
    "configured_search": 4,
    "website_presence_check": 5,
    "kijiji": 6,
}


@dataclass(frozen=True)
class Candidate:
    key: str
    observation: SourceObservationModel
    business: BusinessModel
    niche_id: str


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database = Database(get_settings().database_url)
    with database.session_factory() as session:
        recovery_cutoff = _recovery_cutoff(session)
        legacy_business_ids = _legacy_business_ids(session)
        observations = list(
            session.scalars(
                select(SourceObservationModel)
                .where(
                    SourceObservationModel.business_id.in_(legacy_business_ids),
                    SourceObservationModel.observed_at <= recovery_cutoff,
                )
                .order_by(SourceObservationModel.observed_at, SourceObservationModel.id)
            )
        )
        memberships = _membership_map(session, legacy_business_ids)
        niche_slugs = {
            niche_id: slug
            for niche_id, slug in session.execute(select(NicheModel.id, NicheModel.slug))
        }
        painting_niche_id = session.scalar(
            select(NicheModel.id).where(NicheModel.slug == "home_service_painting")
        )
        if painting_niche_id is None:
            raise RuntimeError("home_service_painting niche is missing")

        latest_by_key: dict[str, SourceObservationModel] = {}
        for observation in observations:
            latest_by_key[_candidate_key(observation)] = observation

        businesses = {
            business.id: business
            for business in session.scalars(
                select(BusinessModel).where(BusinessModel.id.in_(legacy_business_ids))
            )
        }
        candidates: list[Candidate] = []
        unresolved_business_ids: set[str] = set()
        for key, observation in latest_by_key.items():
            niche_ids = memberships.get(observation.business_id, set())
            niche_id = _niche_for_candidate(
                business=businesses[observation.business_id],
                observation=observation,
                niche_ids=niche_ids,
                niche_slugs=niche_slugs,
            )
            if niche_id is None and not niche_ids and _looks_like_painting(
                businesses[observation.business_id], observation
            ):
                niche_id = painting_niche_id
            if niche_id is None:
                unresolved_business_ids.add(observation.business_id)
                continue
            candidates.append(
                Candidate(
                    key=key,
                    observation=observation,
                    business=businesses[observation.business_id],
                    niche_id=niche_id,
                )
            )

        existing_segments = {
            segment.niche_id: segment
            for segment in session.scalars(
                select(BusinessIndexSegmentModel).where(
                    BusinessIndexSegmentModel.market_key == MARKET_KEY
                )
            )
        }
        required_niche_ids = {candidate.niche_id for candidate in candidates}
        missing_niche_ids = required_niche_ids - set(existing_segments)
        existing_candidate_keys = _restored_candidate_keys(session)
        pending_candidates = [
            candidate
            for candidate in candidates
            if candidate.key not in existing_candidate_keys
        ]
        primary_keys = _primary_candidate_keys(pending_candidates)

        summary = {
            "dry_run": not args.apply,
            "legacy_businesses": len(legacy_business_ids),
            "legacy_observations": len(observations),
            "deduplicated_candidates": len(latest_by_key),
            "restorable_candidates": len(candidates),
            "already_restored_candidates": len(candidates) - len(pending_candidates),
            "pending_source_items": len(pending_candidates),
            "primary_business_validations": len(primary_keys),
            "unresolved_businesses": len(unresolved_business_ids),
            "unresolved_business_details": [
                {
                    "business_id": business_id,
                    "display_name": businesses[business_id].display_name,
                    "category_key": businesses[business_id].category_key,
                    "market_key": businesses[business_id].market_key,
                    "candidate_count": sum(
                        observation.business_id == business_id
                        for observation in latest_by_key.values()
                    ),
                    "membership_niches": _niche_slugs(
                        session, memberships.get(business_id, set())
                    ),
                    "candidates": [
                        {
                            "candidate_key": key,
                            "source": observation.source,
                            "query": _query(observation),
                        }
                        for key, observation in latest_by_key.items()
                        if observation.business_id == business_id
                    ],
                }
                for business_id in sorted(unresolved_business_ids)
            ],
            "missing_segments": _niche_slugs(session, missing_niche_ids),
            "source_breakdown": dict(
                sorted(
                    Counter(
                        candidate.observation.source for candidate in pending_candidates
                    ).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
        }
        if not args.apply:
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if unresolved_business_ids:
            raise RuntimeError(
                "Cannot apply recovery with unresolved niche assignments: "
                + ", ".join(sorted(unresolved_business_ids))
            )

        product_id = _recovery_product_id(session, existing_segments.values())
        now = utcnow()
        for niche_id in sorted(missing_niche_ids):
            segment = BusinessIndexSegmentModel(
                id=new_id("index_segment"),
                niche_id=niche_id,
                product_id=product_id,
                market_key=MARKET_KEY,
                market_label=MARKET_LABEL,
                status="active",
                demand_count=0,
                target_business_count=25,
                source_plan=[],
                source_state={},
            )
            session.add(segment)
            session.flush()
            existing_segments[niche_id] = segment

        queue = QueueRepository(session)
        created_items = 0
        queued_validations = 0
        for index, candidate in enumerate(pending_candidates):
            observation = candidate.observation
            payload = _source_item_payload(candidate)
            source_item_value = SourceItemCreate(
                segment_id=existing_segments[candidate.niche_id].id,
                provider_id=observation.source,
                external_id=observation.external_id,
                query=_query(observation),
                source_url=observation.source_url,
                title=payload["title"],
                raw_payload=payload,
                fetched_at=observation.observed_at,
            )
            is_primary = candidate.key in primary_keys
            source_item = SourceItemModel(
                id=new_id("source_item"),
                **source_item_value.model_dump(),
                content_hash=source_item_content_hash(source_item_value),
                state="validating" if is_primary else "identity_resolved",
                business_id=candidate.business.id,
            )
            session.add(source_item)
            session.flush()
            _record_restore_decisions(
                session,
                source_item=source_item,
                candidate=candidate,
                is_primary=is_primary,
            )
            created_items += 1
            if is_primary and args.enqueue:
                queue.enqueue_once(
                    JobType.BUSINESS_OPPORTUNITY_AUDIT,
                    {
                        "source_item_id": source_item.id,
                        "segment_id": source_item.segment_id,
                        "business_id": source_item.business_id,
                    },
                    dedupe_key=f"{source_item.id}:{source_item.business_id}",
                    max_attempts=3,
                    delay_seconds=(queued_validations // args.jobs_per_minute) * 60,
                    commit=False,
                )
                queued_validations += 1
            if (index + 1) % args.commit_batch_size == 0:
                session.commit()
        session.commit()

        summary.update(
            {
                "dry_run": False,
                "created_source_items": created_items,
                "queued_validations": queued_validations,
                "created_segments": _niche_slugs(session, missing_niche_ids),
            }
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _legacy_business_ids(session) -> list[str]:
    normal_item_business_ids: set[str] = set()
    recovery_item_business_ids: set[str] = set()
    for business_id, payload in session.execute(
        select(SourceItemModel.business_id, SourceItemModel.raw_payload).where(
            SourceItemModel.business_id.is_not(None)
        )
    ):
        raw = payload.get("raw") if isinstance(payload, dict) else None
        if isinstance(raw, dict) and raw.get("recovery_marker") == MARKER:
            recovery_item_business_ids.add(business_id)
        else:
            normal_item_business_ids.add(business_id)
    return list(
        session.scalars(
            select(BusinessModel.id)
            .where(
                BusinessModel.id.in_(
                    select(SourceObservationModel.business_id).distinct()
                )
            )
            .where(
                (~BusinessModel.id.in_(normal_item_business_ids))
                | BusinessModel.id.in_(recovery_item_business_ids)
            )
        )
    )


def _recovery_cutoff(session):
    restored_created_at = []
    for created_at, payload in session.execute(
        select(SourceItemModel.created_at, SourceItemModel.raw_payload)
    ):
        raw = payload.get("raw") if isinstance(payload, dict) else None
        if isinstance(raw, dict) and raw.get("recovery_marker") == MARKER:
            restored_created_at.append(created_at)
    return min(restored_created_at) if restored_created_at else utcnow()


def _membership_map(session, business_ids: list[str]) -> dict[str, set[str]]:
    memberships: dict[str, set[str]] = defaultdict(set)
    rows = session.execute(
        select(
            BusinessNicheMembershipModel.business_id,
            BusinessNicheMembershipModel.niche_id,
        ).where(BusinessNicheMembershipModel.business_id.in_(business_ids))
    )
    for business_id, niche_id in rows:
        memberships[business_id].add(niche_id)
    return memberships


def _candidate_key(observation: SourceObservationModel) -> str:
    external_id = (observation.external_id or "").strip()
    source_url = (observation.source_url or "").strip()
    if external_id:
        identity = f"external:{external_id}"
    elif source_url:
        identity = f"url:{source_url}"
    else:
        identity = f"content:{observation.content_hash}"
    return f"{observation.source}:{identity}"


def _restored_candidate_keys(session) -> set[str]:
    keys: set[str] = set()
    for payload in session.scalars(select(SourceItemModel.raw_payload)):
        if not isinstance(payload, dict):
            continue
        raw = payload.get("raw")
        if not isinstance(raw, dict) or raw.get("recovery_marker") != MARKER:
            continue
        key = raw.get("legacy_candidate_key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


def _primary_candidate_keys(candidates: list[Candidate]) -> set[str]:
    by_business: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        by_business[candidate.business.id].append(candidate)
    primary: set[str] = set()
    for business_candidates in by_business.values():
        winner = min(
            business_candidates,
            key=lambda candidate: (
                SOURCE_PRIORITY.get(candidate.observation.source, 99),
                -candidate.observation.observed_at.timestamp(),
                candidate.key,
            ),
        )
        primary.add(winner.key)
    return primary


def _source_item_payload(candidate: Candidate) -> dict[str, Any]:
    observation = candidate.observation
    original = observation.raw_payload if isinstance(observation.raw_payload, dict) else {}
    raw = dict(original)
    raw.update(
        {
            "recovery_marker": MARKER,
            "legacy_candidate_key": candidate.key,
            "legacy_source_observation_id": observation.id,
            "legacy_business_id": candidate.business.id,
            "external_id": observation.external_id,
            "source_url": observation.source_url,
            "phone": candidate.business.phone,
            "address": candidate.business.address,
            "latitude": candidate.business.latitude,
            "longitude": candidate.business.longitude,
        }
    )
    title = _first_text(
        original.get("title"),
        original.get("displayName"),
        candidate.business.display_name,
    )
    return {
        "title": title,
        "url": observation.source_url or candidate.business.website_url,
        "snippet": _first_text(
            original.get("snippet"),
            original.get("description"),
            candidate.business.semantic_text,
        ),
        "geography": _first_text(
            original.get("geography"),
            candidate.business.geography,
            candidate.business.address,
        ),
        "contact_email": _first_text(original.get("contact_email")),
        "source": _normalized_result_source(observation.source),
        "raw": raw,
    }


def _record_restore_decisions(
    session,
    *,
    source_item: SourceItemModel,
    candidate: Candidate,
    is_primary: bool,
) -> None:
    now = utcnow()
    session.add_all(
        [
            SourceItemDecisionModel(
                id=new_id("source_decision"),
                source_item_id=source_item.id,
                stage="relevance",
                decision="accepted",
                reason="Recovered from a preserved legacy source observation.",
                confidence=None,
                details={
                    "recovery_marker": MARKER,
                    "legacy_source_observation_id": candidate.observation.id,
                    "candidate_key": candidate.key,
                },
                actor_type="system",
                actor_id=None,
                created_at=now,
                updated_at=now,
            ),
            SourceItemDecisionModel(
                id=new_id("source_decision"),
                source_item_id=source_item.id,
                stage="identity",
                decision="resolved",
                reason=(
                    "Latest observation retained as the candidate's canonical link; "
                    "current validation is required."
                ),
                confidence=None,
                details={
                    "business_id": candidate.business.id,
                    "resolution": "legacy_latest_observation",
                    "primary_validation_item": is_primary,
                },
                actor_type="system",
                actor_id=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )


def _looks_like_painting(
    business: BusinessModel,
    observation: SourceObservationModel,
) -> bool:
    payload = observation.raw_payload if isinstance(observation.raw_payload, dict) else {}
    text = " ".join(
        str(value or "")
        for value in (
            business.display_name,
            business.category_key,
            observation.query_signature,
            payload.get("query"),
            payload.get("title"),
        )
    ).lower()
    return any(term in text for term in ("paint", "painter", "painting", "decorating"))


def _niche_for_candidate(
    *,
    business: BusinessModel,
    observation: SourceObservationModel,
    niche_ids: set[str],
    niche_slugs: dict[str, str],
) -> str | None:
    if len(niche_ids) == 1:
        return next(iter(niche_ids))
    if not niche_ids:
        return None
    payload = observation.raw_payload if isinstance(observation.raw_payload, dict) else {}
    terms = {
        slug: tuple(spec.trade_terms) for slug, spec in NICHE_BY_SLUG.items()
    }
    evidence_layers = [
        _query(observation),
        " ".join(
            str(value or "")
            for value in (
                payload.get("title"),
                payload.get("snippet"),
                business.display_name,
            )
        ),
    ]
    for layer in evidence_layers:
        text = layer.lower()
        matches = [
            niche_id
            for niche_id in niche_ids
            if any(term in text for term in terms.get(niche_slugs[niche_id], ()))
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def _query(observation: SourceObservationModel) -> str:
    payload = observation.raw_payload if isinstance(observation.raw_payload, dict) else {}
    query = _first_text(payload.get("query"))
    if query:
        return query
    signature = observation.query_signature or ""
    prefix = f"{observation.source}:"
    return signature.removeprefix(prefix) or "legacy source observation"


def _normalized_result_source(source: str) -> str:
    return {
        "google_places_seed": "google_places",
        "openstreetmap_seed": "openstreetmap",
    }.get(source, source)


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _recovery_product_id(session, segments) -> str:
    product_ids = {segment.product_id for segment in segments}
    if len(product_ids) == 1:
        return next(iter(product_ids))
    active_product_ids = list(
        session.scalars(
            select(ProductModel.id)
            .where(ProductModel.archived_at.is_(None))
            .order_by(ProductModel.created_at)
        )
    )
    if len(active_product_ids) == 1:
        return active_product_ids[0]
    raise RuntimeError("Could not select one product for recovery segments")


def _niche_slugs(session, niche_ids: set[str]) -> list[str]:
    if not niche_ids:
        return []
    return sorted(
        session.scalars(select(NicheModel.slug).where(NicheModel.id.in_(niche_ids)))
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the recovery. The default is a read-only dry run.",
    )
    parser.add_argument(
        "--enqueue",
        action="store_true",
        help="Queue one validation and opportunity-audit job per restored business.",
    )
    parser.add_argument(
        "--jobs-per-minute",
        type=int,
        default=25,
        help="Stagger queued validation jobs at this rate (default: 25).",
    )
    parser.add_argument(
        "--commit-batch-size",
        type=int,
        default=250,
        help="Commit this many restored source items at a time (default: 250).",
    )
    args = parser.parse_args(argv)
    if args.enqueue and not args.apply:
        parser.error("--enqueue requires --apply")
    if args.jobs_per_minute < 1 or args.commit_batch_size < 1:
        parser.error("batch sizes must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
