"""Stage published facts whose source observation fails integrity checks.

Dry-run is the default. Pass ``--apply`` only after reviewing the JSON report.
This command never rewrites source payloads or content hashes.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import timedelta
import json
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from business_validation.repository import (  # noqa: E402
    ValidationRepository,
    ValidationResult,
)
from db.models import BusinessFactModel, SourceObservationModel  # noqa: E402
from db.session import Database  # noqa: E402
from shared.utils import utcnow  # noqa: E402
from source_observations.integrity import evaluate_observation_integrity  # noqa: E402


POLICY_VERSION = 1


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    database = Database(get_settings().database_url)
    session = next(database.session())
    try:
        report = stage_invalid_facts(
            session,
            apply=args.apply,
            source=args.source,
            business_id=args.business_id,
            limit=args.limit,
            detail_limit=args.detail_limit,
        )
    finally:
        session.close()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage published facts backed by corrupt source observations."
    )
    parser.add_argument("--source", help="Limit to one exact observation source.")
    parser.add_argument("--business-id", help="Limit to one business.")
    parser.add_argument("--limit", type=int, help="Maximum affected facts to process.")
    parser.add_argument("--detail-limit", type=int, default=100)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write staged fact states and failed integrity validation results.",
    )
    return parser.parse_args(argv)


def stage_invalid_facts(
    session: Session,
    *,
    apply: bool = False,
    source: str | None = None,
    business_id: str | None = None,
    limit: int | None = None,
    detail_limit: int = 100,
) -> dict[str, Any]:
    statement = (
        select(BusinessFactModel, SourceObservationModel)
        .join(
            SourceObservationModel,
            SourceObservationModel.id == BusinessFactModel.source_observation_id,
        )
        .where(BusinessFactModel.quality_state == "published")
        .order_by(BusinessFactModel.observed_at.desc())
    )
    if source:
        statement = statement.where(SourceObservationModel.source == source)
    if business_id:
        statement = statement.where(BusinessFactModel.business_id == business_id)

    affected: list[tuple[BusinessFactModel, SourceObservationModel, tuple[str, ...]]] = []
    for fact, observation in session.execute(statement):
        integrity = evaluate_observation_integrity(
            observation,
            expected_business_id=fact.business_id,
        )
        if integrity.status != "failed":
            continue
        affected.append((fact, observation, integrity.failures))
        if limit is not None and len(affected) >= max(0, limit):
            break

    by_source: Counter[str] = Counter()
    by_fact_key: Counter[str] = Counter()
    details: list[dict[str, Any]] = []
    validation_keys: set[tuple[str, str]] = set()
    now = utcnow()
    for fact, observation, failures in affected:
        by_source[observation.source] += 1
        by_fact_key[fact.fact_key] += 1
        if len(details) < detail_limit:
            details.append(
                {
                    "fact_id": fact.id,
                    "business_id": fact.business_id,
                    "fact_key": fact.fact_key,
                    "observation_id": observation.id,
                    "source": observation.source,
                    "failures": list(failures),
                }
            )
        if not apply:
            continue
        fact.quality_state = "staged"
        fact.quality_policy_version = max(fact.quality_policy_version, 3)
        validation_key = (fact.business_id, observation.id)
        if validation_key in validation_keys:
            continue
        validation_keys.add(validation_key)
        ValidationRepository(session).record(
            ValidationResult(
                business_id=fact.business_id,
                source_item_id=None,
                source_observation_id=observation.id,
                validation_type="observation_integrity",
                status="failed",
                confidence=0,
                reason=" ".join(dict.fromkeys(failures)),
                evidence=evaluate_observation_integrity(
                    observation,
                    expected_business_id=fact.business_id,
                ).evidence,
                validator="source_observation_integrity",
                validator_version=POLICY_VERSION,
                observed_at=now,
                expires_at=now + timedelta(days=30),
            )
        )

    if apply:
        session.commit()
    else:
        session.rollback()
    return {
        "generated_at": now.isoformat(),
        "applied": apply,
        "database_mutated": apply,
        "affected_fact_count": len(affected),
        "affected_business_count": len({fact.business_id for fact, _, _ in affected}),
        "affected_observation_count": len(
            {observation.id for _, observation, _ in affected}
        ),
        "by_source": dict(sorted(by_source.items())),
        "by_fact_key": dict(sorted(by_fact_key.items())),
        "details": details,
    }


if __name__ == "__main__":
    main()
