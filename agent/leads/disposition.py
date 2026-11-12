from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import AudienceResultModel, LeadModel, ProductModel, TerritoryModel


DISMISSED_REVIEW_STATUS = "not_fit"


def dismissed_business_ids(
    session: Session,
    *,
    workspace_id: str,
) -> set[str]:
    """Return canonical businesses dismissed anywhere in a workspace.

    A dismissal is a workspace-level decision about a canonical business, not a
    decision about one saved-search result.  Both result-backed and promoted
    leads are consulted so older workflow records remain authoritative.
    """
    result_business_ids = session.scalars(
        select(AudienceResultModel.business_id)
        .join(TerritoryModel, TerritoryModel.id == AudienceResultModel.audience_id)
        .where(
            TerritoryModel.workspace_id == workspace_id,
            AudienceResultModel.review_status == DISMISSED_REVIEW_STATUS,
        )
    )
    lead_business_ids = session.scalars(
        select(LeadModel.business_id)
        .join(ProductModel, ProductModel.id == LeadModel.product_id)
        .where(
            ProductModel.workspace_id == workspace_id,
            LeadModel.business_id.is_not(None),
            LeadModel.review_status == DISMISSED_REVIEW_STATUS,
        )
    )
    return {
        business_id
        for business_id in [*result_business_ids, *lead_business_ids]
        if business_id
    }


def apply_business_review_status(
    session: Session,
    *,
    workspace_id: str,
    business_id: str,
    review_status: str,
    reviewed_at: datetime,
) -> None:
    """Apply an explicit review decision to every copy of one business.

    This keeps saved-search results and promoted leads consistent.  Restoring a
    business is explicit as well: changing it away from ``not_fit`` clears the
    workspace-level dismissal across its existing workflow records.
    """
    results = session.scalars(
        select(AudienceResultModel)
        .join(TerritoryModel, TerritoryModel.id == AudienceResultModel.audience_id)
        .where(
            TerritoryModel.workspace_id == workspace_id,
            AudienceResultModel.business_id == business_id,
        )
    )
    for result in results:
        result.review_status = review_status
        result.reviewed_at = reviewed_at
        if review_status == DISMISSED_REVIEW_STATUS:
            result.shortlisted_at = None

    leads = session.scalars(
        select(LeadModel)
        .join(ProductModel, ProductModel.id == LeadModel.product_id)
        .where(
            ProductModel.workspace_id == workspace_id,
            LeadModel.business_id == business_id,
        )
    )
    for lead in leads:
        lead.review_status = review_status
        lead.reviewed_at = reviewed_at
        if review_status == DISMISSED_REVIEW_STATUS:
            lead.shortlisted_at = None
