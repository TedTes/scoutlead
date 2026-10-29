#!/usr/bin/env python3
"""Audit configured-search-origin businesses; pass --apply to quarantine them."""

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
from quality.inventory_cleanup import cleanup_search_origin_inventory  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    database = Database(get_settings().database_url)
    with database.session_factory() as session:
        result = cleanup_search_origin_inventory(
            session,
            apply=args.apply,
            limit=args.limit,
        )
    rendered = json.dumps(asdict(result), indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(f"{rendered}\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
