"""Capture websites locally and persist compact manifests as business attributes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from db.models import BusinessModel  # noqa: E402
from db.session import Database  # noqa: E402
from website_capture.playwright_provider import PlaywrightBrowserCapture  # noqa: E402
from website_capture.service import WebsiteCaptureService  # noqa: E402
from website_capture.storage import LocalArtifactStore  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Capture stored business websites locally.")
    parser.add_argument("--business-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--artifact-root", default="artifacts/website-captures")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    settings = get_settings()
    database = Database(settings.database_url)
    generator = database.session()
    session = next(generator)
    try:
        query = (
            select(BusinessModel.id)
            .where(BusinessModel.website_url.is_not(None))
            .order_by(BusinessModel.id)
            .limit(max(1, args.limit))
        )
        if args.business_id:
            query = select(BusinessModel.id).where(BusinessModel.id.in_(args.business_id))
        business_ids = list(session.scalars(query))
        service = WebsiteCaptureService(
            session,
            browser=PlaywrightBrowserCapture(
                timeout_seconds=settings.website_capture_timeout_seconds,
                max_screenshot_height=settings.website_capture_max_height,
            ),
            artifacts=LocalArtifactStore(args.artifact_root),
            freshness_days=settings.website_capture_freshness_days,
        )
        results = []
        for business_id in business_ids:
            try:
                result = service.capture(business_id, force=args.force)
                results.append({
                    "business_id": business_id,
                    "status": "cached" if result["cached"] else "captured",
                    "capture": result["capture"],
                })
            except Exception as exc:
                session.rollback()
                results.append({
                    "business_id": business_id,
                    "status": "failed",
                    "error": str(exc),
                })
        print(json.dumps({"results": results}, indent=2))
    finally:
        generator.close()


if __name__ == "__main__":
    main()
