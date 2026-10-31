"""Revalidate facts listed as repaired in a fact-repair manifest.

Dry-run is the default. Apply mode requires an endpoint lock and a backup path so
the command cannot silently target a different Railway database.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from business_facts.repository import fact_value  # noqa: E402
from db.models import BusinessFactModel, SignalDefinitionModel  # noqa: E402
from db.session import Database  # noqa: E402
from signal_validation.service import SignalValidationService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-output")
    parser.add_argument("--output")
    parser.add_argument("--expected-host")
    parser.add_argument("--expected-port", type=int)
    args = parser.parse_args(argv)

    settings = get_settings()
    endpoint = urlsplit(settings.database_url)
    if args.apply:
        if not args.backup_output:
            parser.error("Apply mode requires --backup-output")
        if not args.expected_host or args.expected_port is None:
            parser.error("Apply mode requires --expected-host and --expected-port")
        if endpoint.hostname != args.expected_host or endpoint.port != args.expected_port:
            parser.error("Configured database does not match the locked endpoint")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    repaired_ids = {
        row["fact_id"]
        for row in manifest.get("details", [])
        if row.get("action") == "repair_from_claim"
    }
    database = Database(settings.database_url)
    with database.session_factory() as session:
        facts = list(
            session.scalars(
                select(BusinessFactModel)
                .where(BusinessFactModel.id.in_(repaired_ids))
                .order_by(BusinessFactModel.id)
            )
        )
        definitions = {
            row.id: row
            for row in session.scalars(
                select(SignalDefinitionModel).where(
                    SignalDefinitionModel.id.in_(
                        {fact.signal_definition_id for fact in facts if fact.signal_definition_id}
                    )
                )
            )
        }
        groups: dict[str, list[str]] = {}
        skipped: list[str] = []
        for fact in facts:
            if fact.signal_definition_id not in definitions:
                skipped.append(fact.id)
                continue
            groups.setdefault(fact.signal_definition_id, []).append(fact.business_id)

        result: dict[str, object] = {
            "dry_run": not args.apply,
            "configured_host": endpoint.hostname,
            "configured_port": endpoint.port,
            "manifest_fact_ids": len(repaired_ids),
            "facts_found": len(facts),
            "facts_grouped": sum(len(ids) for ids in groups.values()),
            "skipped_fact_ids": skipped,
            "definitions": {},
        }
        if args.apply:
            backup = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "configured_host": endpoint.hostname,
                "configured_port": endpoint.port,
                "facts": [_snapshot(fact) for fact in facts],
            }
            _write_json(args.backup_output, backup)
            service = SignalValidationService(session)
            validation_results: dict[str, object] = {}
            for definition_id, business_ids in groups.items():
                definition = definitions[definition_id]
                validation_results[definition.key] = service.validate(
                    definition.id,
                    expected_version=definition.version,
                    business_ids=business_ids,
                )
            result["definitions"] = validation_results
        else:
            result["definitions"] = {
                definitions[definition_id].key: len(business_ids)
                for definition_id, business_ids in groups.items()
            }

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        _write_json(args.output, result)
    else:
        print(rendered)
    return 0


def _snapshot(fact: BusinessFactModel) -> dict[str, object]:
    return {
        "id": fact.id,
        "business_id": fact.business_id,
        "fact_key": fact.fact_key,
        "signal_definition_id": fact.signal_definition_id,
        "value": fact_value(fact),
        "confidence": fact.confidence,
        "resolution_state": fact.resolution_state,
        "quality_state": fact.quality_state,
        "quality_policy_version": fact.quality_policy_version,
        "source_observation_id": fact.source_observation_id,
        "supporting_claim_ids": list(fact.supporting_claim_ids or []),
        "observed_at": fact.observed_at.isoformat(),
        "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
    }


def _write_json(path_value: str, value: object) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(value, indent=2, sort_keys=True)}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
