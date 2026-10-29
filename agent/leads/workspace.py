from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from audience_runs.schemas import AudienceLeadRead
from audience_runs.service import AudienceRunService
from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    LeadModel,
    ProductModel,
    TerritoryModel,
)
from leads.schemas import LeadRead, WorkspaceLeadCounts


WorkspaceLeadView = Literal["inbox", "shortlisted", "contacted", "dismissed", "this_week", "all"]


class WorkspaceLeadPage(BaseModel):
    items: list[LeadRead | AudienceLeadRead]
    total: int
    limit: int
    offset: int
    counts: WorkspaceLeadCounts


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: Literal["lead", "audience_result"]
    model: LeadModel | AudienceResultModel
    key: str
    review_status: str
    shortlisted_at: datetime | None
    contacted_at: datetime | None
    contact_policy_status: str
    created_at: datetime
    updated_at: datetime
    searchable: str

    @property
    def dismissed(self) -> bool:
        return self.review_status == "not_fit" or self.contact_policy_status != "allowed"

    @property
    def priority(self) -> tuple[int, int, int, float]:
        return (
            int(self.shortlisted_at is not None),
            int(self.contacted_at is not None),
            int(self.kind == "audience_result"),
            self.updated_at.timestamp(),
        )


class WorkspaceLeadService:
    """One read model for workspace counts and paginated lead lists."""

    def __init__(self, session: Session, *, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def counts(self) -> WorkspaceLeadCounts:
        return self._counts(self._canonical_candidates())

    def page(
        self,
        *,
        view: WorkspaceLeadView = "inbox",
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> WorkspaceLeadPage:
        canonical = self._canonical_candidates()
        filtered = [item for item in canonical if self._matches_view(item, view)]
        needle = (search or "").strip().casefold()
        if needle:
            filtered = [item for item in filtered if needle in item.searchable]
        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        selected = filtered[offset : offset + limit]
        audience_service = AudienceRunService(self.session, workspace_id=self.workspace_id)
        items: list[LeadRead | AudienceLeadRead] = []
        for candidate in selected:
            if candidate.kind == "audience_result":
                item = audience_service._lead_read(candidate.model).model_dump()
            else:
                item = LeadRead.model_validate(candidate.model).model_dump()
            item["shortlisted_at"] = candidate.shortlisted_at
            item["last_contacted_at"] = candidate.contacted_at
            item["review_status"] = candidate.review_status
            item["contact_policy_status"] = candidate.contact_policy_status
            items.append(
                AudienceLeadRead.model_validate(item)
                if candidate.kind == "audience_result"
                else LeadRead.model_validate(item)
            )
        return WorkspaceLeadPage(
            items=items,
            total=len(filtered),
            limit=limit,
            offset=offset,
            counts=self._counts(canonical),
        )

    def _canonical_candidates(self) -> list[_Candidate]:
        candidates = [*self._audience_candidates(), *self._legacy_candidates()]
        canonical: dict[str, _Candidate] = {}
        for candidate in candidates:
            current = canonical.get(candidate.key)
            if current is None:
                canonical[candidate.key] = candidate
                continue
            representative = candidate if candidate.priority > current.priority else current
            canonical[candidate.key] = replace(
                representative,
                review_status=(
                    "not_fit" if current.dismissed or candidate.dismissed
                    else representative.review_status
                ),
                shortlisted_at=current.shortlisted_at or candidate.shortlisted_at,
                contacted_at=current.contacted_at or candidate.contacted_at,
                contact_policy_status=(
                    current.contact_policy_status
                    if current.contact_policy_status != "allowed"
                    else candidate.contact_policy_status
                ),
                created_at=min(current.created_at, candidate.created_at),
                updated_at=max(current.updated_at, candidate.updated_at),
                searchable=f"{current.searchable} {candidate.searchable}",
            )
        return list(canonical.values())

    def _audience_candidates(self) -> list[_Candidate]:
        audience_ids = list(
            self.session.scalars(
                select(TerritoryModel.id).where(
                    TerritoryModel.workspace_id == self.workspace_id,
                    TerritoryModel.status != "archived",
                )
            )
        )
        if not audience_ids:
            return []
        runs = list(
            self.session.scalars(
                select(AudienceRunModel)
                .where(
                    AudienceRunModel.workspace_id == self.workspace_id,
                    AudienceRunModel.audience_id.in_(audience_ids),
                    select(AudienceResultModel.id)
                    .where(AudienceResultModel.run_id == AudienceRunModel.id)
                    .exists(),
                )
                .order_by(AudienceRunModel.created_at.desc())
            )
        )
        latest_run_by_audience: dict[str, str] = {}
        for run in runs:
            latest_run_by_audience.setdefault(run.audience_id, run.id)
        latest_run_ids = set(latest_run_by_audience.values())
        current_results = list(
            self.session.scalars(
                select(AudienceResultModel).where(AudienceResultModel.run_id.in_(latest_run_ids))
            )
        ) if latest_run_ids else []
        current_keys = {(item.audience_id, item.business_id) for item in current_results}
        managed_history = list(
            self.session.scalars(
                select(AudienceResultModel)
                .where(
                    AudienceResultModel.audience_id.in_(audience_ids),
                    AudienceResultModel.run_id.not_in(latest_run_ids),
                    or_(
                        AudienceResultModel.reviewed_at.is_not(None),
                        AudienceResultModel.shortlisted_at.is_not(None),
                        AudienceResultModel.contacted_at.is_not(None),
                        AudienceResultModel.outreach_lead_id.is_not(None),
                    ),
                )
                .order_by(AudienceResultModel.updated_at.desc())
            )
        ) if latest_run_ids else []
        included_history: set[tuple[str, str]] = set()
        selected = list(current_results)
        for item in managed_history:
            key = (item.audience_id, item.business_id)
            if key in current_keys or key in included_history:
                continue
            included_history.add(key)
            selected.append(item)
        outreach_lead_ids = [item.outreach_lead_id for item in selected if item.outreach_lead_id]
        outreach_leads = {
            lead.id: lead
            for lead in self.session.scalars(
                select(LeadModel).where(LeadModel.id.in_(outreach_lead_ids))
            )
        } if outreach_lead_ids else {}
        candidates: list[_Candidate] = []
        for item in selected:
            snapshot = item.match_snapshot or {}
            outreach_lead = outreach_leads.get(item.outreach_lead_id or "")
            policy = outreach_lead.contact_policy_status if outreach_lead else "allowed"
            contacted_at = outreach_lead.last_contacted_at if outreach_lead else item.contacted_at
            searchable = " ".join(
                str(value or "")
                for value in (
                    snapshot.get("title"),
                    snapshot.get("geography"),
                    snapshot.get("snippet"),
                )
            ).casefold()
            candidates.append(
                _Candidate(
                    kind="audience_result",
                    model=item,
                    key=f"business:{item.business_id}",
                    review_status=item.review_status,
                    shortlisted_at=item.shortlisted_at,
                    contacted_at=contacted_at,
                    contact_policy_status=policy,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                    searchable=searchable,
                )
            )
        return candidates

    def _legacy_candidates(self) -> list[_Candidate]:
        leads = list(
            self.session.scalars(
                select(LeadModel)
                .join(ProductModel, ProductModel.id == LeadModel.product_id)
                .where(ProductModel.workspace_id == self.workspace_id)
            )
        )
        return [
            _Candidate(
                kind="lead",
                model=lead,
                key=f"business:{lead.business_id}" if lead.business_id else f"lead:{lead.id}",
                review_status=lead.review_status,
                shortlisted_at=lead.shortlisted_at,
                contacted_at=lead.last_contacted_at or lead.latest_outcome_at,
                contact_policy_status=lead.contact_policy_status,
                created_at=lead.created_at,
                updated_at=lead.updated_at,
                searchable=" ".join(
                    value or "" for value in (lead.company_name, lead.geography, lead.description)
                ).casefold(),
            )
            for lead in leads
        ]

    @staticmethod
    def _matches_view(candidate: _Candidate, view: WorkspaceLeadView) -> bool:
        if view == "dismissed":
            return candidate.dismissed
        if candidate.dismissed:
            return False
        if view == "shortlisted":
            return candidate.shortlisted_at is not None
        if view == "contacted":
            return candidate.contacted_at is not None
        if view == "this_week":
            created_at = candidate.created_at
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            return created_at >= cutoff
        return True

    @staticmethod
    def _counts(candidates: list[_Candidate]) -> WorkspaceLeadCounts:
        active = [item for item in candidates if not item.dismissed]
        return WorkspaceLeadCounts(
            leads=len(active),
            shortlisted=sum(item.shortlisted_at is not None for item in active),
            contacted=sum(item.contacted_at is not None for item in active),
            dismissed=sum(item.dismissed for item in candidates),
            all=len(candidates),
        )
