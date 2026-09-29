#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select


ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "agent"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from db.models import NicheModel  # noqa: E402


class SignalVocabulary(BaseModel):
    tags: list[str] = Field(min_length=10, max_length=20)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = [
            "_".join(value.strip().lower().split())
            for value in values
            if value.strip()
        ]
        unique = list(dict.fromkeys(normalized))
        if len(unique) < 10:
            raise ValueError("at least 10 unique signal tags are required")
        return unique[:20]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and persist controlled qualification signals for niches."
    )
    parser.add_argument("--niche", help="Only process this niche slug.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing signal vocabularies.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated values without saving them.",
    )
    args = parser.parse_args()

    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        statement = select(NicheModel).where(NicheModel.active.is_(True))
        if args.niche:
            statement = statement.where(NicheModel.slug == args.niche)
        niches = list(session.scalars(statement.order_by(NicheModel.slug)))
        for niche in niches:
            if niche.signal_vocabulary and not args.force:
                print(f"skip {niche.slug}: vocabulary already exists")
                continue
            vocabulary = services.llm.generate_object(
                task="niche_signal_vocabulary",
                system=(
                    "Create a stable controlled vocabulary of observable public-business "
                    "signals. Return concise snake_case tags only."
                ),
                prompt=(
                    f"Niche: {niche.label}\n"
                    f"Category: {niche.category or niche.label}\n"
                    "Return 10 to 20 distinct signals that can be supported by a business "
                    "website, public listing, or public review. Do not include inferred pain, "
                    "intent, contact availability, or subjective quality."
                ),
                response_model=SignalVocabulary,
                context={"niche_id": niche.id, "niche_slug": niche.slug},
            )
            print(f"{niche.slug}: {', '.join(vocabulary.tags)}")
            if not args.dry_run:
                niche.signal_vocabulary = vocabulary.tags
        if not args.dry_run:
            session.commit()
    finally:
        session_generator.close()


if __name__ == "__main__":
    main()
