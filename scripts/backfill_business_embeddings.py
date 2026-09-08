"""Backfill canonical business embeddings.

Examples:
    python scripts/backfill_business_embeddings.py --dry-run
    python scripts/backfill_business_embeddings.py --limit 1000 --batch-size 100
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from seeding.embedding_backfill import (  # noqa: E402
    BusinessEmbeddingBackfillService,
    EmbeddingBackfillSummary,
    OpenAIEmbeddingBatchClient,
)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY") or settings.openai_api_key
    if not api_key and not args.dry_run:
        raise SystemExit("OPENAI_API_KEY is required unless --dry-run is set")

    services = create_app_services(settings)
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        client = OpenAIEmbeddingBatchClient(
            api_key=api_key or "dry-run",
            model=args.model or settings.openai_embedding_model,
            dimension=args.dimension or settings.embedding_dimension,
            timeout_seconds=args.timeout_seconds,
        )
        summary = BusinessEmbeddingBackfillService(
            session,
            embedding_client=client,
        ).backfill(
            limit=args.limit,
            batch_size=args.batch_size,
            force=args.force,
            dry_run=args.dry_run,
        )
    finally:
        session_generator.close()

    print_summary(summary)
    if summary.failed_batches:
        raise SystemExit(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill business embedding vectors.")
    parser.add_argument("--limit", type=int, help="Maximum businesses to backfill.")
    parser.add_argument("--batch-size", type=int, default=100, help="OpenAI embeddings batch size.")
    parser.add_argument("--force", action="store_true", help="Rebuild even existing embeddings.")
    parser.add_argument("--dry-run", action="store_true", help="Count eligible rows without writing.")
    parser.add_argument("--model", help="Embedding model. Defaults to OPENAI_EMBEDDING_MODEL/settings.")
    parser.add_argument("--dimension", type=int, help="Embedding dimension. Defaults to settings.")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--openai-api-key", help="OpenAI API key. Defaults to env/settings.")
    return parser.parse_args(argv)


def print_summary(summary: EmbeddingBackfillSummary) -> None:
    print(f"Dry run: {'yes' if summary.dry_run else 'no'}")
    print(f"Rows scanned: {summary.scanned}")
    print(f"Rows eligible: {summary.eligible}")
    print(f"Rows embedded: {summary.embedded}")
    print(f"Rows skipped: {summary.skipped}")
    print(f"Failed batches: {summary.failed_batches}")


if __name__ == "__main__":
    main()
