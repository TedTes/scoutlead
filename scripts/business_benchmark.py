#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

from app.config import get_settings  # noqa: E402
from benchmarks.evaluator import evaluate_records  # noqa: E402
from benchmarks.importer import import_reviewed_records  # noqa: E402
from benchmarks.io import read_jsonl, write_jsonl  # noqa: E402
from benchmarks.sampler import sample_businesses  # noqa: E402
from db.session import Database  # noqa: E402


DEFAULT_NICHES = [
    "home_service_painting",
    "home_service_hvac",
    "home_service_roofing",
    "home_service_plumbing",
    "home_service_electrical",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample and evaluate ScoutLead benchmarks.")
    commands = parser.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("sample", help="Export an unlabeled stratified JSONL sample.")
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--per-niche", type=int, default=50)
    sample.add_argument("--market", default="toronto")
    sample.add_argument("--niche", action="append", dest="niches")
    evaluate = commands.add_parser("evaluate", help="Evaluate a reviewed JSONL benchmark.")
    evaluate.add_argument("--input", type=Path, required=True)
    evaluate.add_argument("--output", type=Path)
    evaluate.add_argument("--minimum-reviewed", type=int, default=200)
    evaluate.add_argument("--minimum-labels", type=int, default=50)
    evaluate.add_argument("--minimum-scope-reviewed", type=int, default=30)
    evaluate.add_argument("--require-niche", action="append", default=[])
    evaluate.add_argument("--require-market", action="append", default=[])
    apply_labels = commands.add_parser(
        "import",
        help="Import reviewed benchmark labels into runtime quality gates.",
    )
    apply_labels.add_argument("--input", type=Path, required=True)
    apply_labels.add_argument(
        "--apply",
        action="store_true",
        help="Persist labels. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    if args.command == "sample":
        database = Database(get_settings().database_url)
        with database.session_factory() as session:
            records = sample_businesses(
                session,
                niche_slugs=args.niches or DEFAULT_NICHES,
                per_niche=max(1, args.per_niche),
                market_key=args.market,
            )
        write_jsonl(args.output, records)
        print(json.dumps({"output": str(args.output), "record_count": len(records)}))
        return 0

    if args.command == "import":
        database = Database(get_settings().database_url)
        with database.session_factory() as session:
            summary = import_reviewed_records(
                session,
                read_jsonl(args.input),
                dry_run=not args.apply,
            )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    report = evaluate_records(
        read_jsonl(args.input),
        minimum_reviewed=max(1, args.minimum_reviewed),
        minimum_labels_per_metric=max(1, args.minimum_labels),
        required_niches=set(args.require_niche),
        required_markets=set(args.require_market),
        minimum_scope_reviewed=max(1, args.minimum_scope_reviewed),
    )
    rendered = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
