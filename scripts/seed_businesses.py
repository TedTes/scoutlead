"""Import public business seed data into the canonical ScoutLead business store.

Usage:
    python scripts/seed_businesses.py --file data/seeds/home-service-painting-toronto.sample.jsonl --dry-run
    python scripts/seed_businesses.py --file data/seeds/home-service-painting-toronto.sample.jsonl --batch-id home-service-painting-toronto-v1
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from pydantic import ValidationError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from seeding.schemas import BusinessSeedImportSummary, BusinessSeedInput, BusinessSeedRowError  # noqa: E402
from seeding.service import BusinessSeedService  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    seeds, errors, rows_read = read_seed_file(
        args.file,
        default_market=args.seed_market,
        default_niche=args.seed_niche,
        default_source=args.source,
        limit=args.limit,
    )
    batch_id = args.batch_id or args.file.stem

    if args.dry_run:
        summary = BusinessSeedImportSummary(
            batch_id=batch_id,
            dry_run=True,
            rows_read=rows_read,
            rows_valid=len(seeds),
            skipped_rows=len(errors),
            errors=errors,
        )
        print_summary(summary)
        if errors:
            raise SystemExit(1)
        return

    settings = get_settings()
    services = create_app_services(settings)
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        summary = BusinessSeedService(session, embedding=services.embedding).import_seeds(
            seeds,
            batch_id=batch_id,
        )
        summary.rows_read = rows_read
        summary.rows_valid = len(seeds)
        summary.skipped_rows = len(errors)
        summary.errors = errors
    finally:
        session_generator.close()

    print_summary(summary)
    if errors:
        raise SystemExit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed canonical public businesses.")
    parser.add_argument("--file", type=Path, required=True, help="CSV, JSONL, or NDJSON seed file.")
    parser.add_argument("--batch-id", help="Stable seed batch identifier. Defaults to the file stem.")
    parser.add_argument("--source", default="manual_seed", help="Default source for rows without source.")
    parser.add_argument("--seed-niche", default="home_service_painting", help="Default niche label.")
    parser.add_argument("--seed-market", help="Default market/geography, e.g. Toronto/GTA.")
    parser.add_argument("--limit", type=int, help="Maximum rows to read from the file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without DB writes.")
    return parser.parse_args(argv)


def read_seed_file(
    path: Path,
    *,
    default_market: str | None,
    default_niche: str,
    default_source: str,
    limit: int | None,
) -> tuple[list[BusinessSeedInput], list[BusinessSeedRowError], int]:
    if not path.exists():
        raise SystemExit(f"Seed file not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return read_csv_seed_file(
            path,
            default_market=default_market,
            default_niche=default_niche,
            default_source=default_source,
            limit=limit,
        )
    if suffix in {".jsonl", ".ndjson"}:
        return read_jsonl_seed_file(
            path,
            default_market=default_market,
            default_niche=default_niche,
            default_source=default_source,
            limit=limit,
        )
    raise SystemExit("Seed file must be .csv, .jsonl, or .ndjson")


def read_jsonl_seed_file(
    path: Path,
    *,
    default_market: str | None,
    default_niche: str,
    default_source: str,
    limit: int | None,
) -> tuple[list[BusinessSeedInput], list[BusinessSeedRowError], int]:
    seeds: list[BusinessSeedInput] = []
    errors: list[BusinessSeedRowError] = []
    rows_read = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if limit is not None and rows_read >= limit:
                break
            rows_read += 1
            try:
                raw_row = json.loads(stripped)
                if not isinstance(raw_row, dict):
                    raise ValueError("row must be a JSON object")
                seeds.append(
                    build_seed(
                        raw_row,
                        default_market=default_market,
                        default_niche=default_niche,
                        default_source=default_source,
                    )
                )
            except (ValueError, ValidationError) as exc:
                errors.append(BusinessSeedRowError(row_number=line_number, message=error_message(exc)))
    return seeds, errors, rows_read


def read_csv_seed_file(
    path: Path,
    *,
    default_market: str | None,
    default_niche: str,
    default_source: str,
    limit: int | None,
) -> tuple[list[BusinessSeedInput], list[BusinessSeedRowError], int]:
    seeds: list[BusinessSeedInput] = []
    errors: list[BusinessSeedRowError] = []
    rows_read = 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            if limit is not None and rows_read >= limit:
                break
            rows_read += 1
            try:
                seeds.append(
                    build_seed(
                        dict(row),
                        default_market=default_market,
                        default_niche=default_niche,
                        default_source=default_source,
                    )
                )
            except (ValueError, ValidationError) as exc:
                errors.append(BusinessSeedRowError(row_number=row_number, message=error_message(exc)))
    return seeds, errors, rows_read


def build_seed(
    data: dict[str, Any],
    *,
    default_market: str | None,
    default_niche: str,
    default_source: str,
) -> BusinessSeedInput:
    cleaned = {key: value for key, value in data.items() if key and value not in (None, "")}
    cleaned.setdefault("source", default_source)
    cleaned.setdefault("seed_niche", default_niche)
    if default_market:
        cleaned.setdefault("seed_market", default_market)
        cleaned.setdefault("geography", default_market)
    raw = cleaned.get("raw")
    if isinstance(raw, str) and raw.strip():
        parsed_raw = json.loads(raw)
        if not isinstance(parsed_raw, dict):
            raise ValueError("raw must be a JSON object")
        cleaned["raw"] = parsed_raw
    return BusinessSeedInput.model_validate(cleaned)


def error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError) and exc.errors():
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first.get("loc", ()))
        message = str(first.get("msg") or exc)
        return f"{location}: {message}" if location else message
    return str(exc)


def print_summary(summary: BusinessSeedImportSummary) -> None:
    print(f"Seed batch: {summary.batch_id}")
    print(f"Dry run: {'yes' if summary.dry_run else 'no'}")
    print(f"Rows read: {summary.rows_read}")
    print(f"Rows valid: {summary.rows_valid}")
    print(f"Businesses created: {summary.businesses_created}")
    print(f"Businesses updated: {summary.businesses_updated}")
    print(f"Contacts created: {summary.contacts_created}")
    print(f"Source observations created: {summary.source_observations_created}")
    print(f"Skipped rows: {summary.skipped_rows}")
    if summary.errors:
        print()
        print("Errors:")
        for error in summary.errors:
            print(f"  row {error.row_number}: {error.message}")


if __name__ == "__main__":
    main()

