"""Assess stored businesses locally; does not fetch websites or call paid APIs."""

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
from website_assessments.service import WebsiteAssessmentService  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Assess websites from stored evidence.")
    parser.add_argument("--business-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv)

    database = Database(get_settings().database_url)
    generator = database.session()
    session = next(generator)
    try:
        query = select(BusinessModel.id).order_by(BusinessModel.id).limit(args.limit)
        if args.business_id:
            query = select(BusinessModel.id).where(BusinessModel.id.in_(args.business_id))
        ids = list(session.scalars(query))
        service = WebsiteAssessmentService(session)
        results = [service.assess(business_id, commit=False) for business_id in ids]
        if args.persist:
            session.commit()
        else:
            session.rollback()
        print(json.dumps({"persisted": args.persist, "results": results}, indent=2))
    finally:
        generator.close()


if __name__ == "__main__":
    main()
