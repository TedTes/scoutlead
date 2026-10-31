"""Export read-only city/category data-readiness bundles.

The command never calls external providers and never writes to the database. It
records explicit request budgets that can be reviewed before a separate
collection run is authorized.

Example:
    python scripts/prepare_city_category_data.py \
      --market Toronto=43.6532,-79.3832 \
      --market Vancouver=49.2827,-123.1207 \
      --category home_service_landscaping \
      --category home_service_painting \
      --category home_service_hvac \
      --target-count 100 \
      --provider-budget google_places=10 \
      --provider-budget openstreetmap=1
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from data_readiness.export import (  # noqa: E402
    MarketScope,
    ProviderBudget,
    export_city_category,
)
from db.session import Database  # noqa: E402


DEFAULT_MARKETS = (
    MarketScope("Toronto", 43.6532, -79.3832, 25.0),
    MarketScope("Vancouver", 49.2827, -123.1207, 25.0),
)
DEFAULT_CATEGORIES = (
    "home_service_landscaping",
    "home_service_painting",
    "home_service_hvac",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    markets = [_parse_market(value, radius_km=args.radius_km) for value in args.market]
    if not markets:
        markets = [
            MarketScope(row.label, row.latitude, row.longitude, args.radius_km)
            for row in DEFAULT_MARKETS
        ]
    categories = list(dict.fromkeys(args.category or DEFAULT_CATEGORIES))
    budgets = [_parse_budget(value) for value in args.provider_budget]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    database = Database(get_settings().database_url)
    generated = []
    review_sample = []
    with database.session_factory() as session:
        for market in markets:
            for category in categories:
                bundle = export_city_category(
                    session,
                    market=market,
                    niche_slug=category,
                    target_count=max(1, args.target_count),
                    candidate_limit=max(args.target_count, args.candidate_limit),
                    provider_budgets=budgets,
                )
                prefix = f"{_slug(market.label)}__{_slug(category)}"
                paths = {}
                for key in ("validated", "uncertain", "rejected"):
                    path = output_dir / f"{prefix}__{key}.json"
                    _write_json(path, bundle[key])
                    paths[key] = str(path)
                manifest_path = output_dir / f"{prefix}__manifest.json"
                _write_json(manifest_path, bundle["manifest"])
                paths["manifest"] = str(manifest_path)
                generated.append(
                    {
                        "market": market.label,
                        "category": category,
                        "counts": bundle["manifest"]["counts"],
                        "files": paths,
                    }
                )
                for bucket in ("validated", "uncertain", "rejected"):
                    review_sample.extend(
                        {
                            "market": market.label,
                            "category": category,
                            "bucket": bucket,
                            "business": row,
                        }
                        for row in bundle[bucket][:10]
                    )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database_mutated": False,
        "external_requests_executed": 0,
        "bundles": generated,
    }
    summary_path = output_dir / "summary.json"
    _write_json(summary_path, summary)
    review_sample_path = output_dir / "review-sample.json"
    _write_json(review_sample_path, review_sample)
    print(
        json.dumps(
            {
                **summary,
                "summary_file": str(summary_path),
                "review_sample_file": str(review_sample_path),
            },
            indent=2,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare non-mutating city/category data-readiness JSON exports."
    )
    parser.add_argument(
        "--market",
        action="append",
        default=[],
        metavar="LABEL=LAT,LNG",
        help="Market center; repeat for more markets. Defaults to Toronto and Vancouver.",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help="Niche slug; repeat for more categories. Defaults to landscaping, painting, HVAC.",
    )
    parser.add_argument("--radius-km", type=float, default=25.0)
    parser.add_argument("--target-count", type=int, default=100)
    parser.add_argument("--candidate-limit", type=int, default=400)
    parser.add_argument(
        "--provider-budget",
        action="append",
        default=[],
        metavar="PROVIDER=MAX_REQUESTS",
        help="Dry-run request cap recorded in each manifest; no request is executed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/readiness/current"),
    )
    return parser.parse_args(argv)


def _parse_market(value: str, *, radius_km: float) -> MarketScope:
    try:
        label, coordinates = value.split("=", 1)
        latitude_text, longitude_text = coordinates.split(",", 1)
        latitude = float(latitude_text)
        longitude = float(longitude_text)
    except ValueError as exc:
        raise SystemExit(f"Invalid --market {value!r}; expected LABEL=LAT,LNG") from exc
    if not label.strip() or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise SystemExit(f"Invalid --market {value!r}; coordinates are out of range")
    return MarketScope(label.strip(), latitude, longitude, max(0.1, radius_km))


def _parse_budget(value: str) -> ProviderBudget:
    try:
        provider_id, limit_text = value.split("=", 1)
        limit = int(limit_text)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid --provider-budget {value!r}; expected PROVIDER=MAX_REQUESTS"
        ) from exc
    if not provider_id.strip() or limit < 0:
        raise SystemExit(f"Invalid --provider-budget {value!r}")
    return ProviderBudget(provider_id.strip(), limit)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
