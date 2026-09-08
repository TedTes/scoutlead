"""Collect Google Places results into a seed JSONL file.

Examples:
    python scripts/collect_google_places_seed.py \
        --output data/seeds/home-service-painting-toronto.public.jsonl \
        --target-count 100

    python scripts/collect_google_places_seed.py \
        --output data/seeds/home-service-painting-toronto.public.jsonl \
        --target-count 1000 \
        --max-requests 250
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from pydantic import ValidationError  # noqa: E402

from app.config import get_settings  # noqa: E402
from seeding.google_places import (  # noqa: E402
    GooglePlacesSeedCollector,
    GooglePlacesSeedQuery,
    build_home_service_painting_queries,
    seed_dedupe_key,
)
from seeding.schemas import BusinessSeedInput  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    api_key = args.api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or get_settings().google_places_api_key
    if not api_key:
        raise SystemExit("GOOGLE_PLACES_API_KEY is required to collect Google Places seed data")

    existing = read_existing_seeds(args.output) if args.merge_existing else []
    queries = build_queries(args)
    collector = GooglePlacesSeedCollector(
        api_key=api_key,
        endpoint=args.endpoint,
        timeout_seconds=args.timeout_seconds,
        page_delay_seconds=args.page_delay_seconds,
    )
    collection = collector.collect(
        queries,
        target_count=args.target_count,
        existing=existing,
        max_requests=args.max_requests,
        max_pages_per_query=args.max_pages_per_query,
    )
    write_jsonl(args.output, collection.rows)

    added = max(0, len(collection.rows) - len(existing))
    print(f"Output: {args.output}")
    print(f"Rows written: {len(collection.rows)}")
    print(f"Existing rows kept: {len(existing)}")
    print(f"New rows collected: {added}")
    print(f"Queries attempted: {collection.queries_attempted}")
    print(f"Google Places requests: {collection.requests_made}")
    if len(collection.rows) < args.target_count:
        print(
            "Target not reached. Increase --max-requests, broaden --city/--query, "
            "or review API/rate-limit responses."
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Google Places seed data into JSONL.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSONL path.")
    parser.add_argument("--target-count", type=int, default=100, help="Total rows to write.")
    parser.add_argument(
        "--max-requests",
        type=int,
        default=80,
        help="Hard cap on Google Places API requests. Text Search can return up to 20 rows per request.",
    )
    parser.add_argument(
        "--max-pages-per-query",
        type=int,
        default=3,
        help="Maximum paginated Text Search pages to request for each query.",
    )
    parser.add_argument("--market", default="Toronto/GTA", help="Seed market label.")
    parser.add_argument("--region-code", default="CA", help="Google Places region code.")
    parser.add_argument(
        "--city",
        action="append",
        default=[],
        help="City/geography to include. Can be passed more than once.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Exact Google Places text query. Can be passed more than once.",
    )
    parser.add_argument(
        "--queries-file",
        type=Path,
        help="Text file with one exact Google Places text query per line.",
    )
    parser.add_argument(
        "--merge-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep and dedupe existing rows in the output file.",
    )
    parser.add_argument("--api-key", help="Google Places API key. Defaults to env/settings.")
    parser.add_argument("--endpoint", help="Override Google Places Text Search endpoint.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--page-delay-seconds", type=float, default=0.5)
    return parser.parse_args(argv)


def build_queries(args: argparse.Namespace) -> list[GooglePlacesSeedQuery]:
    exact_queries = list(args.query)
    if args.queries_file:
        exact_queries.extend(read_query_file(args.queries_file))
    if exact_queries:
        return [
            GooglePlacesSeedQuery(
                text_query=query,
                seed_market=args.market,
                region_code=args.region_code,
            )
            for query in exact_queries
            if query.strip()
        ]
    if args.city:
        return build_home_service_painting_queries(
            seed_market=args.market,
            region_code=args.region_code,
            cities=args.city,
        )
    return build_home_service_painting_queries(
        seed_market=args.market,
        region_code=args.region_code,
    )


def read_query_file(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Query file not found: {path}")
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def read_existing_seeds(path: Path) -> list[BusinessSeedInput]:
    if not path.exists():
        return []
    rows: list[BusinessSeedInput] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                parsed = json.loads(stripped)
                if not isinstance(parsed, dict):
                    raise ValueError("row must be a JSON object")
                seed = BusinessSeedInput.model_validate(parsed)
            except (ValueError, ValidationError) as exc:
                raise SystemExit(f"{path}:{line_number}: {exc}") from exc
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
