from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from db.models import BusinessNicheMembershipModel, SeedBatchModel, SourceObservationModel


QUARANTINED_BATCH_STATUSES = frozenset({"quarantined", "retired"})


def active_membership_condition():
    quarantined_batch = (
        select(SeedBatchModel.id)
        .where(
            SeedBatchModel.id == BusinessNicheMembershipModel.seed_batch_id,
            SeedBatchModel.status.in_(QUARANTINED_BATCH_STATUSES),
        )
        .exists()
    )
    return or_(
        BusinessNicheMembershipModel.seed_batch_id.is_(None),
        ~quarantined_batch,
    )


def observation_is_quarantined(
    session: Session,
    observation: SourceObservationModel,
) -> bool:
    batch_id = observation_batch_id(observation.raw_payload)
    if not batch_id:
        return False
    quarantined = session.info.setdefault("quarantined_seed_batch_ids", set())
    if batch_id in quarantined:
        return True
    batch = session.get(SeedBatchModel, batch_id)
    if batch and batch.status in QUARANTINED_BATCH_STATUSES:
        quarantined.add(batch_id)
        return True
    return False


def observation_batch_id(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("seed_batch_id") or "").strip()
    return value or None
