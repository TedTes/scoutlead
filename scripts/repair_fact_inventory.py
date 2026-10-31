#!/usr/bin/env python3
"""Repair current fact provenance from intact claims; dry-run by default."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from business_facts.repository import fact_value  # noqa: E402
from db.models import BusinessFactModel  # noqa: E402
from db.session import Database  # noqa: E402
from quality.fact_repair import repair_current_facts  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--limit", type=int, default=25000)
    parser.add_argument("--output")
    parser.add_argument("--backup-output")
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.apply and settings.environment == "production" and not args.allow_production:
        parser.error("Refusing production repair without --allow-production")
    if args.apply and not args.backup_output:
        parser.error("Apply mode requires --backup-output")
    database = Database(settings.database_url)
    with database.session_factory() as session:
        if args.apply:
            planned = repair_current_facts(
                session,
                apply=False,
                limit=args.limit,
                include_details=True,
            )
            affected_ids = {
                row["fact_id"]
                for row in planned.details
                if row["action"] in {"repair_from_claim", "delete_irrecoverable"}
            }
            facts = list(
                session.scalars(
                    select(BusinessFactModel)
                    .where(BusinessFactModel.id.in_(affected_ids))
                    .order_by(BusinessFactModel.id)
                )
            )
            backup = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "environment": settings.environment,
                "planned": asdict(planned),
                "facts": [_fact_snapshot(fact) for fact in facts],
            }
            backup_path = Path(args.backup_output)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(
                f"{json.dumps(backup, indent=2, sort_keys=True)}\n",
                encoding="utf-8",
            )
        summary = repair_current_facts(
            session,
            apply=args.apply,
            limit=args.limit,
            include_details=args.details,
        )
    rendered = json.dumps(asdict(summary), indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def _fact_snapshot(fact: BusinessFactModel) -> dict[str, object]:
    return {
        "id": fact.id,
        "business_id": fact.business_id,
        "fact_key": fact.fact_key,
        "signal_definition_id": fact.signal_definition_id,
        "value": fact_value(fact),
        "value_type": fact.value_type,
        "confidence": fact.confidence,
        "resolution_state": fact.resolution_state,
        "supporting_claim_ids": list(fact.supporting_claim_ids or []),
        "quality_state": fact.quality_state,
        "quality_policy_version": fact.quality_policy_version,
        "observed_at": fact.observed_at.isoformat(),
        "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
        "source_observation_id": fact.source_observation_id,
        "resolver_version": fact.resolver_version,
    }


if __name__ == "__main__":
    raise SystemExit(main())
