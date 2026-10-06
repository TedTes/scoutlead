"""Quarantine seed batches while preserving their complete audit history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import func, select, update

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from app.config import get_settings  # noqa: E402
from app.dependencies import create_app_services  # noqa: E402
from db.models import (  # noqa: E402
    BusinessFactModel,
    BusinessNicheMembershipModel,
    SeedBatchModel,
    SourceObservationModel,
)
from seeding.batches import observation_batch_id  # noqa: E402
from shared.utils import utcnow  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    services = create_app_services(get_settings())
    session_generator = services.db.session()
    session = next(session_generator)
    try:
        batches = [
            batch
            for batch_id in args.batch_id
            if (batch := session.get(SeedBatchModel, batch_id)) is not None
        ]
        selected = {batch.id for batch in batches}
        selected_observations = [
            observation
            for observation in session.scalars(select(SourceObservationModel))
            if observation_batch_id(observation.raw_payload) in selected
        ]
        observation_ids = {observation.id for observation in selected_observations}
        business_ids = {observation.business_id for observation in selected_observations}
        memberships = (
            int(
                session.scalar(
                    select(func.count())
                    .select_from(BusinessNicheMembershipModel)
                    .where(BusinessNicheMembershipModel.seed_batch_id.in_(selected))
                )
                or 0
            )
            if selected
            else 0
        )
        if args.apply:
            for batch in batches:
                batch.status = "quarantined"
            session.flush()
            now = utcnow()
            if observation_ids:
                result = session.execute(
                    update(BusinessFactModel)
                    .where(BusinessFactModel.source_observation_id.in_(observation_ids))
                    .values(expires_at=now)
                )
                expired_facts = int(result.rowcount or 0)
            else:
                expired_facts = 0
            session.commit()
        else:
            expired_facts = 0
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry_run",
                    "requested_batches": sorted(set(args.batch_id)),
                    "found_batches": sorted(selected),
                    "observations_preserved": len(selected_observations),
                    "memberships_suppressed": memberships,
                    "businesses_suppressed": len(business_ids),
                    "facts_expired": expired_facts,
                },
                indent=2,
                sort_keys=True,
            )
        )
    finally:
        session_generator.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", action="append", required=True)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main()
