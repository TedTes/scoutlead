#!/usr/bin/env python3
"""Publish useful canonical facts and remove unusable rows; dry-run by default."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.session import Database  # noqa: E402
from quality.fact_usability import clean_canonical_facts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.apply and settings.environment == "production" and not args.allow_production:
        parser.error("Refusing production cleanup without --allow-production")

    database = Database(settings.database_url)
    with database.session_factory() as session:
        result = clean_canonical_facts(
            session,
            apply=args.apply,
            limit=args.limit,
        )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
