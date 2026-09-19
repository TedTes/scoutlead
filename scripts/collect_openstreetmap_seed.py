"""Collect public OpenStreetMap businesses into a niche seed JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from seeding.openstreetmap import (  # noqa: E402
    DEFAULT_OVERPASS_ENDPOINT,
    NICHE_PLANS,
    OpenStreetMapSeedCollector,
    seed_dedupe_key,
)
from seeding.schemas import BusinessSeedInput  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    plan = NICHE_PLANS[args.niche]
    existing = read_existing_seeds(args.output) if args.merge_existing else []
    result = OpenStreetMapSeedCollector(
        endpoint=args.endpoint,
        timeout_seconds=args.timeout_seconds,
    ).collect(
        plan,
        seed_market=args.market,
        target_count=args.target_count,
        existing=existing,
    )
    write_jsonl(args.output, result.rows)
    print(f"Output: {args.output}")
    print(f"Rows written: {len(result.rows)}")
    print(f"OpenStreetMap elements read: {result.elements_read}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect OpenStreetMap niche seed data.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--niche", choices=sorted(NICHE_PLANS), required=True)
    parser.add_argument("--market", default="Toronto/GTA")
    parser.add_argument("--target-count", type=int, default=50)
    parser.add_argument("--endpoint", default=DEFAULT_OVERPASS_ENDPOINT)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument(
        "--merge-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args(argv)


def read_existing_seeds(path: Path) -> list[BusinessSeedInput]:
    if not path.exists():
        return []
    rows: list[BusinessSeedInput] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            seed = BusinessSeedInput.model_validate(json.loads(stripped))
            key = seed_dedupe_key(seed)
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            rows.append(seed)
    return rows


def write_jsonl(path: Path, rows: list[BusinessSeedInput]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.model_dump(mode="json", exclude_none=True), sort_keys=True))
            handle.write("\n")


if __name__ == "__main__":
    main()
