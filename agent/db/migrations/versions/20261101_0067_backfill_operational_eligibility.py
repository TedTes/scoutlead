"""backfill operational eligibility and current record checks

Revision ID: 20261101_0067
Revises: 20261101_0066
Create Date: 2026-11-01

Existing businesses must not become ineligible merely because the operational
attribute was introduced after their source observations were collected.  This
replays the deterministic synchronizer and validators against the strongest
current observation for every indexed business.  It does not manufacture
evidence: unknown operational status remains unknown and missing checks remain
pending.
"""

from alembic import op
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from business_facts.core_attributes import sync_observed_business_attributes
from business_validation.validation import BusinessValidationService
from db.models import (
    BusinessIndexSegmentModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    SourceObservationModel,
)


revision = "20261101_0067"
down_revision = "20261101_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    session = Session(bind=op.get_bind(), expire_on_commit=False)
    provider_priority = case(
        (SourceObservationModel.source == "google_places", 0),
        (SourceObservationModel.source == "openstreetmap", 1),
        (SourceObservationModel.source == "yellowpages", 2),
        (SourceObservationModel.source.like("apify%"), 3),
        else_=9,
    )
    observations = session.scalars(
        select(SourceObservationModel).order_by(
            SourceObservationModel.business_id,
            provider_priority,
            SourceObservationModel.observed_at.desc(),
        )
    ).all()
    strongest = {}
    for observation in observations:
        strongest.setdefault(observation.business_id, observation)

    rows = session.execute(
        select(BusinessModel, BusinessIndexSegmentModel)
        .join(
            BusinessNicheMembershipModel,
            BusinessNicheMembershipModel.business_id == BusinessModel.id,
        )
        .join(
            BusinessIndexSegmentModel,
            (
                (BusinessIndexSegmentModel.niche_id == BusinessNicheMembershipModel.niche_id)
                & (BusinessIndexSegmentModel.market_key == BusinessNicheMembershipModel.market_key)
            ),
        )
    ).all()
    validator = BusinessValidationService(session)
    synced = set()
    for index, (business, segment) in enumerate(rows, start=1):
        observation = strongest.get(business.id)
        if observation is None:
            continue
        if business.id not in synced:
            sync_observed_business_attributes(
                session,
                business=business,
                observation=observation,
            )
            synced.add(business.id)
        validator.record(
            validator.evaluate_observation(
                business=business,
                observation=observation,
                segment=segment,
            ),
            commit=False,
        )
        if index % 100 == 0:
            session.flush()
    session.flush()


def downgrade() -> None:
    # Facts and validation results are evidence records and may have been used
    # after this migration.  They are intentionally preserved on downgrade.
    pass
