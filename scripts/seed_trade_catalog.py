"""Idempotently seed the canonical trade catalog into the niches table.

Usage:
    PYTHONPATH=agent python scripts/seed_trade_catalog.py --dry-run
    PYTHONPATH=agent python scripts/seed_trade_catalog.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.session import Database  # noqa: E402
from niches.seeding import load_trade_catalog, seed_trade_catalog  # noqa: E402


DEFAULT_CATALOG = ROOT / "data" / "seeds" / "canonical-trade-catalog.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Seed the canonical trade catalog into niches."
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    entries = load_trade_catalog(args.file)
    database = Database(get_settings().database_url)
    session_generator = database.session()
    session = next(session_generator)
    try:
        summary = seed_trade_catalog(session, entries, dry_run=args.dry_run)
    finally:
        session_generator.close()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
