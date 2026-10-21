"""Backfill audience centers and canonical business coordinates.

Dry-run is the default. Use --apply to persist provider-backed coordinates.
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
from app.dependencies import create_app_services  # noqa: E402
from territories.coordinate_backfill import CoordinateBackfillService  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persist resolved coordinates.")
    parser.add_argument("--limit", type=int, help="Maximum rows scanned per entity type.")
    args = parser.parse_args(argv)

    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        summary = CoordinateBackfillService(
            session,
            geocoder=services.market_geocoder,
        ).run(dry_run=not args.apply, limit=args.limit)
    finally:
        session_generator.close()
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
