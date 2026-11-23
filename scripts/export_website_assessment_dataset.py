"""Export model-ready website features and human labels without external API calls.

Usage:
    PYTHONPATH=agent python scripts/export_website_assessment_dataset.py \
      --output website-assessment-dataset.json
"""

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
from business_attributes.repository import attribute_value  # noqa: E402
from db.models import BusinessAttributeModel, BusinessModel  # noqa: E402
from db.session import Database  # noqa: E402
from website_assessments.features import extract_website_features  # noqa: E402
from website_assessments.service import TRAINING_LABEL_KEY  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export labeled website assessments.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-unlabeled", action="store_true")
    args = parser.parse_args(argv)

    database = Database(get_settings().database_url)
    generator = database.session()
    session = next(generator)
    try:
        businesses = list(session.scalars(select(BusinessModel).order_by(BusinessModel.id)))
        rows = list(
            session.scalars(
                select(BusinessAttributeModel).where(
                    BusinessAttributeModel.business_id.in_([item.id for item in businesses])
                )
            )
        ) if businesses else []
        by_business: dict[str, dict[str, BusinessAttributeModel]] = {}
        for row in rows:
            by_business.setdefault(row.business_id, {})[row.attribute_key] = row
        examples = []
        for business in businesses:
            attributes = by_business.get(business.id, {})
            label = attribute_value(attributes.get(TRAINING_LABEL_KEY))
            if not isinstance(label, dict) and not args.include_unlabeled:
                continue
            examples.append(
                {
                    "business": {
                        "id": business.id,
                        "name": business.display_name,
                        "website_url": business.website_url,
                    },
                    "features": extract_website_features(business, attributes).as_dict(),
                    "label": label,
                }
            )
        payload = {
            "schema_version": 1,
            "example_count": len(examples),
            "examples": examples,
        }
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.output), "example_count": len(examples)}))
    finally:
        generator.close()


if __name__ == "__main__":
    main()
