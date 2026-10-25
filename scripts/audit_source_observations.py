"""Read-only integrity audit for source observations.

Examples:
    python scripts/audit_source_observations.py
    python scripts/audit_source_observations.py --source google_places --details
    python scripts/audit_source_observations.py --stale-days 60 --output observation-audit.json

Output is always JSON so it can be saved, compared, or used as a release artifact.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import timedelta
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.models import (  # noqa: E402
    BusinessFactModel,
    FactClaimModel,
    SourceObservationModel,
)
from db.session import Database  # noqa: E402
from shared.utils import utcnow  # noqa: E402
from source_observations.integrity import evaluate_observation_integrity  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    database = Database(get_settings().database_url)
    session = next(database.session())
    try:
        report = build_audit(
            session,
            source=args.source,
            business_id=args.business_id,
            stale_days=args.stale_days,
            include_details=args.details,
            detail_limit=args.detail_limit,
        )
    finally:
        session.close()

    rendered = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit source-observation integrity without changing data."
    )
    parser.add_argument("--source", help="Exact source name to audit.")
    parser.add_argument("--business-id", help="Audit one business only.")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=90,
        help="Treat observations older than this as uncertain (default: 90).",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Include affected observation IDs and check details.",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=100,
        help="Maximum affected observations and duplicate groups to include.",
    )
    parser.add_argument("--output", help="Also write the JSON report to this path.")
    return parser.parse_args(argv)


def build_audit(
    session: Session,
    *,
    source: str | None = None,
    business_id: str | None = None,
    stale_days: int = 90,
    include_details: bool = False,
    detail_limit: int = 100,
) -> dict[str, Any]:
    statement = select(SourceObservationModel).order_by(
        SourceObservationModel.observed_at.desc()
    )
    if source:
        statement = statement.where(SourceObservationModel.source == source)
    if business_id:
        statement = statement.where(SourceObservationModel.business_id == business_id)
    observations = list(session.scalars(statement))
    report = audit_observations(
        observations,
        stale_days=stale_days,
        include_details=include_details,
        detail_limit=detail_limit,
    )
    observation_ids = [row.id for row in observations]
    claims_statement = select(FactClaimModel)
    facts_statement = select(BusinessFactModel)
    if source or business_id:
        claims_statement = claims_statement.where(
            FactClaimModel.source_observation_id.in_(observation_ids)
        )
        facts_statement = facts_statement.where(
            BusinessFactModel.source_observation_id.in_(observation_ids)
        )
    report["downstream_reliability"] = audit_downstream_links(
        observations,
        session.scalars(claims_statement),
        session.scalars(facts_statement),
        include_details=include_details,
        detail_limit=detail_limit,
        validate_supporting_claims=not (source or business_id),
    )
    return report


def audit_observations(
    observations: Iterable[object],
    *,
    stale_days: int = 90,
    include_details: bool = False,
    detail_limit: int = 100,
) -> dict[str, Any]:
    rows = list(observations)
    now = utcnow()
    status_counts: Counter[str] = Counter()
    issue_counts: Counter[str] = Counter()
    issue_source_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    source_counts: Counter[str] = Counter()
    affected: list[dict[str, Any]] = []
    content_groups: defaultdict[tuple[str, str, str], list[str]] = defaultdict(list)
    external_groups: defaultdict[tuple[str, str], list[object]] = defaultdict(list)

    for observation in rows:
        result = evaluate_observation_integrity(
            observation,
            now=now,
            stale_after=timedelta(days=max(1, stale_days)),
            require_locator=True,
        )
        status_counts[result.status] += 1
        source_name = str(getattr(observation, "source", "") or "")
        source_counts[source_name or "(missing)"] += 1
        failing_checks = [
            check
            for check in result.checks
            if check.status in {"failed", "uncertain"}
        ]
        for check in failing_checks:
            issue_key = f"{check.status}:{check.name}"
            issue_counts[issue_key] += 1
            issue_source_counts[source_name or "(missing)"][issue_key] += 1
        if include_details and failing_checks and len(affected) < detail_limit:
            affected.append(
                {
                    "observation_id": getattr(observation, "id", None),
                    "business_id": getattr(observation, "business_id", None),
                    "source": source_name,
                    "status": result.status,
                    "issues": [check.as_evidence() for check in failing_checks],
                }
            )

        content_hash = str(getattr(observation, "content_hash", "") or "")
        if source_name and content_hash:
            content_groups[
                (
                    str(getattr(observation, "business_id", "") or ""),
                    source_name,
                    content_hash,
                )
            ].append(str(getattr(observation, "id", "") or ""))
        external_id = str(getattr(observation, "external_id", "") or "").strip()
        if source_name and external_id:
            external_groups[(source_name, external_id)].append(observation)

    duplicate_content = [
        {
            "business_id": key[0],
            "source": key[1],
            "content_hash": key[2],
            "count": len(ids),
            "observation_ids": ids if include_details else [],
        }
        for key, ids in content_groups.items()
        if len(ids) > 1
    ]
    external_collisions = []
    for (source_name, external_id), grouped in external_groups.items():
        business_ids = sorted(
            {str(getattr(row, "business_id", "") or "") for row in grouped}
        )
        if len(business_ids) > 1:
            external_collisions.append(
                {
                    "source": source_name,
                    "external_id": external_id,
                    "business_count": len(business_ids),
                    "business_ids": business_ids if include_details else [],
                }
            )

    duplicate_content.sort(key=lambda item: item["count"], reverse=True)
    external_collisions.sort(key=lambda item: item["business_count"], reverse=True)
    report: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "policy": {
            "stale_days": max(1, stale_days),
            "locator_required_for_audit": True,
            "database_mutated": False,
        },
        "summary": {
            "observations_scanned": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
            "issue_counts": dict(sorted(issue_counts.items())),
            "issue_counts_by_source": {
                source_name: dict(sorted(counts.items()))
                for source_name, counts in sorted(issue_source_counts.items())
            },
            "source_counts": dict(sorted(source_counts.items())),
            "duplicate_content_groups": len(duplicate_content),
            "cross_business_external_id_collisions": len(external_collisions),
        },
        "duplicate_content_groups": duplicate_content[:detail_limit],
        "cross_business_external_id_collisions": external_collisions[:detail_limit],
    }
    if include_details:
        report["affected_observations"] = affected
    return report


def audit_downstream_links(
    observations: Iterable[object],
    claims: Iterable[object],
    facts: Iterable[object],
    *,
    include_details: bool = False,
    detail_limit: int = 100,
    validate_supporting_claims: bool = True,
) -> dict[str, Any]:
    """Check that claims and canonical facts still point to coherent evidence."""

    observation_by_id = {
        str(getattr(row, "id", "")): row for row in observations
    }
    claim_rows = list(claims)
    claim_by_id = {str(getattr(row, "id", "")): row for row in claim_rows}
    fact_rows = list(facts)
    issue_counts: Counter[str] = Counter()
    affected: list[dict[str, Any]] = []

    def issue(kind: str, row_type: str, row: object, detail: str) -> None:
        issue_counts[kind] += 1
        if include_details and len(affected) < detail_limit:
            affected.append(
                {
                    "type": row_type,
                    "id": getattr(row, "id", None),
                    "business_id": getattr(row, "business_id", None),
                    "issue": kind,
                    "detail": detail,
                }
            )

    for claim in claim_rows:
        observation = observation_by_id.get(
            str(getattr(claim, "source_observation_id", ""))
        )
        if observation is None:
            issue(
                "claim_missing_observation",
                "fact_claim",
                claim,
                "Claim does not resolve to an audited source observation.",
            )
        elif getattr(observation, "business_id", None) != getattr(
            claim, "business_id", None
        ):
            issue(
                "claim_business_mismatch",
                "fact_claim",
                claim,
                "Claim and source observation belong to different businesses.",
            )

    integrity_by_observation_id: dict[str, str] = {}
    for fact in fact_rows:
        observation_id = str(getattr(fact, "source_observation_id", "") or "")
        observation = observation_by_id.get(observation_id)
        if not observation_id:
            issue(
                "fact_missing_source_observation",
                "business_fact",
                fact,
                "Canonical fact has no primary source observation.",
            )
        elif observation is None:
            issue(
                "fact_unresolved_source_observation",
                "business_fact",
                fact,
                "Canonical fact does not resolve to an audited source observation.",
            )
        else:
            if getattr(observation, "business_id", None) != getattr(
                fact, "business_id", None
            ):
                issue(
                    "fact_business_mismatch",
                    "business_fact",
                    fact,
                    "Canonical fact and source observation belong to different businesses.",
                )
            integrity_status = integrity_by_observation_id.setdefault(
                observation_id,
                evaluate_observation_integrity(observation).status,
            )
            if (
                getattr(fact, "quality_state", None) == "published"
                and integrity_status == "failed"
            ):
                issue(
                    "published_fact_with_invalid_observation",
                    "business_fact",
                    fact,
                    "Published fact depends on an observation that fails integrity checks.",
                )

        if not validate_supporting_claims:
            continue
        for claim_id in list(getattr(fact, "supporting_claim_ids", None) or []):
            claim = claim_by_id.get(str(claim_id))
            if claim is None:
                issue(
                    "fact_missing_supporting_claim",
                    "business_fact",
                    fact,
                    f"Supporting claim {claim_id!r} is missing.",
                )
            elif getattr(claim, "business_id", None) != getattr(
                fact, "business_id", None
            ):
                issue(
                    "fact_supporting_claim_business_mismatch",
                    "business_fact",
                    fact,
                    "Supporting claim belongs to a different business.",
                )

    report: dict[str, Any] = {
        "claims_scanned": len(claim_rows),
        "facts_scanned": len(fact_rows),
        "issue_counts": dict(sorted(issue_counts.items())),
        "critical_issue_count": sum(
            count
            for name, count in issue_counts.items()
            if name
            in {
                "claim_business_mismatch",
                "fact_business_mismatch",
                "fact_supporting_claim_business_mismatch",
                "published_fact_with_invalid_observation",
            }
        ),
    }
    if include_details:
        report["affected_records"] = affected
    return report


if __name__ == "__main__":
    main()
