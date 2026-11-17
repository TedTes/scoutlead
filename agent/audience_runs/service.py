from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from audience_runs.schemas import (
    AudienceLeadRead,
    AudienceResultRead,
    AudienceResultUpdate,
    AudienceRunRead,
    AudienceRunState,
)
from canonical.normalization import normalize_domain, normalize_email, normalize_phone
from db.models import (
    AudienceResultModel,
    BusinessModel,
    ContactSuppressionModel,
    LeadModel,
    NicheModel,
    TerritoryModel,
)
from leads.disposition import apply_business_review_status, dismissed_business_ids
from leads.repository import LeadRepository
from leads.schemas import ContactPolicyStatus, LeadContactPolicyUpdate, LeadReviewStatus, LeadUpdate
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow
from suppressions.repository import ContactSuppressionRepository
from territories.matching import ProfileMatchService


class AudienceRunService:
    """Maintain the current match set for a saved search.

    The old implementation persisted every execution in ``audience_runs``.  A
    saved search now stores its current execution state on ``territories`` and
    ``audience_results`` contains only the current matches.  The existing HTTP
    routes still accept a ``run_id`` for compatibility; that value is the saved
    search id.
    """

    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def create(
        self,
        audience_id: str,
        *,
        deadline_minutes: int = 10,
        commit: bool = True,
    ) -> TerritoryModel:
        audience = self._audience(audience_id)
        now = utcnow()
        audience.match_state = AudienceRunState.QUEUED.value
        audience.match_requested_count = audience.batch_size
        audience.match_new_result_count = 0
        audience.match_deadline_at = now + timedelta(minutes=max(1, deadline_minutes))
        audience.match_started_at = None
        audience.match_completed_at = None
        audience.match_failure_reason = None
        if commit:
            self.session.commit()
            self.session.refresh(audience)
        else:
            self.session.flush()
        return audience

    def process(self, run_id: str) -> tuple[TerritoryModel, bool]:
        """Match a saved search using stored business attributes only."""
        audience = self._audience(run_id)
        now = utcnow()
        audience.match_state = AudienceRunState.MATCHING.value
        audience.match_started_at = now
        audience.match_index_snapshot_at = now
        audience.match_failure_reason = None
        self.session.flush()

        niches = _territory_niches(self.session, audience)
        dismissed = dismissed_business_ids(
            self.session, workspace_id=audience.workspace_id
        )
        rows = ProfileMatchService(self.session).match(
            profile=audience,
            niche_ids=[niche.id for niche in niches],
            # The saved search stores its first requested page.  Ranking and
            # hydration must not expand that into an 8x candidate batch.
            limit=audience.match_requested_count,
            exclude_business_ids=dismissed,
        )

        existing = {
            result.business_id: result
            for result in self.session.scalars(
                select(AudienceResultModel).where(
                    AudienceResultModel.audience_id == audience.id
                )
            )
        }
        for temporary_rank, result in enumerate(existing.values(), start=1):
            result.rank_position = -temporary_rank
        self.session.flush()

        selected = rows[: audience.match_requested_count]
        selected_ids: set[str] = set()
        new_count = 0
        for rank, row in enumerate(selected, start=1):
            business_id = _business_id(row)
            selected_ids.add(business_id)
            result = existing.get(business_id)
            if result is None:
                new_count += 1
                result = AudienceResultModel(
                    id=new_id("audience_result"),
                    audience_id=audience.id,
                    business_id=business_id,
                    rank_position=rank,
                    is_new=True,
                    match_snapshot=row,
                )
                self.session.add(result)
            else:
                result.rank_position = rank
                result.is_new = False
                result.match_snapshot = row
        for business_id, result in existing.items():
            if business_id not in selected_ids:
                self.session.delete(result)

        audience.match_result_count = len(selected)
        audience.match_new_result_count = new_count
        audience.match_state = (
            AudienceRunState.READY.value
            if len(selected) >= audience.match_requested_count
            else AudienceRunState.PARTIAL.value
        )
        audience.match_completed_at = now
        audience.last_run_at = now
        self.session.commit()
        self.session.refresh(audience)
        return audience, False

    def get_read(self, run_id: str) -> AudienceRunRead:
        audience = self._audience(run_id)
        results = list(
            self.session.scalars(
                select(AudienceResultModel)
                .where(AudienceResultModel.audience_id == audience.id)
                .order_by(AudienceResultModel.rank_position)
            )
        )
        dismissed = dismissed_business_ids(
            self.session, workspace_id=audience.workspace_id
        )
        results = [row for row in results if row.business_id not in dismissed]
        return self._run_read(audience, results)

    def latest_for_audience(self, audience_id: str) -> AudienceRunRead | None:
        audience = self._audience(audience_id)
        return self._run_read(
            audience,
            list(
                self.session.scalars(
                    select(AudienceResultModel)
                    .where(AudienceResultModel.audience_id == audience.id)
                    .order_by(AudienceResultModel.rank_position)
                )
            ),
        )

    def latest_leads_for_audience(
        self,
        audience_id: str,
        *,
        page_size: int | None = None,
        after_rank: int | None = None,
    ) -> list[AudienceLeadRead]:
        leads, _ = self.latest_lead_page(
            audience_id,
            page_size=page_size,
            after_rank=after_rank,
        )
        return leads

    def latest_lead_page(
        self,
        audience_id: str,
        *,
        page_size: int | None = 25,
        after_rank: int | None = None,
    ) -> tuple[list[AudienceLeadRead], int | None]:
        audience = self._audience(audience_id)
        dismissed = dismissed_business_ids(
            self.session, workspace_id=audience.workspace_id
        )
        statement = select(AudienceResultModel).where(
            AudienceResultModel.audience_id == audience.id
        )
        if dismissed:
            statement = statement.where(
                AudienceResultModel.business_id.not_in(dismissed)
            )
        if after_rank is not None:
            statement = statement.where(
                AudienceResultModel.rank_position > after_rank
            )
        statement = statement.order_by(AudienceResultModel.rank_position)
        if page_size is not None:
            statement = statement.limit(max(1, page_size) + 1)
        rows = list(self.session.scalars(statement))
        has_more = page_size is not None and len(rows) > page_size
        page = rows[:page_size] if page_size is not None else rows
        if not page:
            return [], None

        business_ids = [row.business_id for row in page]
        businesses = {
            business.id: business
            for business in self.session.scalars(
                select(BusinessModel).where(BusinessModel.id.in_(business_ids))
            )
        }
        lead_ids = [row.outreach_lead_id for row in page if row.outreach_lead_id]
        leads = {
            lead.id: lead
            for lead in (
                self.session.scalars(
                    select(LeadModel).where(LeadModel.id.in_(lead_ids))
                )
                if lead_ids
                else []
            )
        }
        suppression_identifiers = {
            identifier
            for row in page
            for identifier in self._suppression_identifiers(
                row,
                business=businesses.get(row.business_id),
            )
        }
        suppression_conditions = [
            and_(
                ContactSuppressionModel.kind == kind,
                ContactSuppressionModel.value == value,
            )
            for kind, value in suppression_identifiers
        ]
        suppressions = (
            list(
                self.session.scalars(
                    select(ContactSuppressionModel)
                    .where(or_(*suppression_conditions))
                    .where(
                        or_(
                            ContactSuppressionModel.scope == "global",
                            and_(
                                ContactSuppressionModel.scope == "workspace",
                                ContactSuppressionModel.workspace_id
                                == audience.workspace_id,
                            ),
                            ContactSuppressionModel.product_id == audience.product_id,
                        )
                    )
                    .order_by(ContactSuppressionModel.created_at.desc())
                )
            )
            if suppression_conditions
            else []
        )
        serialized = [
            self._lead_read(
                row,
                audience=audience,
                business=businesses.get(row.business_id),
                lead=leads.get(row.outreach_lead_id),
                suppressions=suppressions,
                preloaded=True,
            )
            for row in page
        ]
        next_cursor = page[-1].rank_position if has_more else None
        return serialized, next_cursor

    def remaining_lead_count(self, audience_id: str) -> int:
        audience = self._audience(audience_id)
        dismissed = dismissed_business_ids(
            self.session, workspace_id=audience.workspace_id
        )
        statement = (
            select(func.count(AudienceResultModel.id))
            .outerjoin(
                LeadModel,
                AudienceResultModel.outreach_lead_id == LeadModel.id,
            )
            .where(AudienceResultModel.audience_id == audience.id)
            .where(
                or_(
                    LeadModel.id.is_(None),
                    and_(
                        LeadModel.shortlisted_at.is_(None),
                        LeadModel.last_contacted_at.is_(None),
                        LeadModel.review_status != LeadReviewStatus.NOT_FIT.value,
                    ),
                )
            )
        )
        if dismissed:
            statement = statement.where(
                AudienceResultModel.business_id.not_in(dismissed)
            )
        return int(self.session.scalar(statement) or 0)

    def lead_count(self, audience_id: str) -> int:
        audience = self._audience(audience_id)
        dismissed = dismissed_business_ids(
            self.session, workspace_id=audience.workspace_id
        )
        statement = select(func.count(AudienceResultModel.id)).where(
            AudienceResultModel.audience_id == audience.id
        )
        if dismissed:
            statement = statement.where(
                AudienceResultModel.business_id.not_in(dismissed)
            )
        return int(self.session.scalar(statement) or 0)

    def update_result(self, result_id: str, update: AudienceResultUpdate) -> AudienceLeadRead:
        result = self._result(result_id)
        audience = self._audience(result.audience_id)
        values = update.model_dump(exclude_unset=True)
        now = utcnow()

        if values.get("shortlisted"):
            suppression = ContactSuppressionRepository(self.session).find_match(
                product_id=audience.product_id,
                workspace_id=audience.workspace_id,
                identifiers=self._suppression_identifiers(result),
            )
            if suppression is not None:
                raise ConflictError(
                    "business is blocked from outreach",
                    {
                        "result_id": result.id,
                        "contact_policy_status": suppression.status,
                        "user_message": "This business is marked do-not-contact and cannot be shortlisted.",
                    },
                )

        from audience_runs.outreach import AudienceOutreachService

        lead_read = AudienceOutreachService(
            self.session, workspace_id=self.workspace_id
        ).promote(result.id)
        lead_update = LeadUpdate.model_validate(
            {
                key: values[key]
                for key in ("review_status", "review_note", "shortlisted")
                if key in values
            }
        )
        LeadRepository(self.session, workspace_id=self.workspace_id).update(
            lead_read.id, lead_update
        )
        if "review_status" in values and values["review_status"] is not None:
            status = values["review_status"]
            normalized = str(status.value if hasattr(status, "value") else status)
            apply_business_review_status(
                self.session,
                workspace_id=audience.workspace_id,
                business_id=result.business_id,
                review_status=normalized,
                reviewed_at=now,
            )
        return self._lead_read(result)

    def update_contact_policy(
        self, result_id: str, update: LeadContactPolicyUpdate
    ) -> AudienceLeadRead:
        result = self._result(result_id)
        audience = self._audience(result.audience_id)
        identifiers = self._suppression_identifiers(result)
        suppressions = ContactSuppressionRepository(self.session)
        if update.status == ContactPolicyStatus.ALLOWED:
            suppressions.clear_policy(
                product_id=audience.product_id,
                workspace_id=audience.workspace_id,
                identifiers=identifiers,
            )
        else:
            suppressions.set_policy(
                product_id=audience.product_id,
                workspace_id=audience.workspace_id,
                identifiers=identifiers,
                status=update.status,
                reason=update.reason,
                scope=update.scope,
                source="audience_review",
            )
            if result.outreach_lead_id:
                LeadRepository(self.session, workspace_id=self.workspace_id).update(
                    result.outreach_lead_id, LeadUpdate(shortlisted=False)
                )
        return self._lead_read(result)

    def _audience(self, audience_id: str) -> TerritoryModel:
        audience = self.session.get(TerritoryModel, audience_id)
        if audience is None or (
            self.workspace_id is not None and audience.workspace_id != self.workspace_id
        ):
            raise NotFoundError("audience not found", {"audience_id": audience_id})
        return audience

    def _result(self, result_id: str) -> AudienceResultModel:
        result = self.session.get(AudienceResultModel, result_id)
        if result is None:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        self._audience(result.audience_id)
        return result

    def _run_read(
        self, audience: TerritoryModel, results: list[AudienceResultModel]
    ) -> AudienceRunRead:
        now = utcnow()
        return AudienceRunRead(
            id=audience.id,
            audience_id=audience.id,
            criteria_version=audience.criteria_version,
            state=AudienceRunState(audience.match_state),
            requested_count=audience.match_requested_count,
            result_count=audience.match_result_count,
            new_result_count=audience.match_new_result_count,
            index_snapshot_at=audience.match_index_snapshot_at,
            deadline_at=audience.match_deadline_at or now,
            started_at=audience.match_started_at,
            completed_at=audience.match_completed_at,
            failure_reason=audience.match_failure_reason,
            outreach_campaign_id=audience.outreach_campaign_id,
            results=[self._result_read(row) for row in results],
            created_at=audience.created_at,
            updated_at=audience.updated_at,
        )

    def _result_read(self, result: AudienceResultModel) -> AudienceResultRead:
        lead = self.session.get(LeadModel, result.outreach_lead_id) if result.outreach_lead_id else None
        return AudienceResultRead(
            id=result.id,
            run_id=result.audience_id,
            audience_id=result.audience_id,
            business_id=result.business_id,
            rank_position=result.rank_position,
            is_new=result.is_new,
            match_snapshot=result.match_snapshot,
            review_status=LeadReviewStatus(lead.review_status) if lead else LeadReviewStatus.UNREVIEWED,
            review_note=lead.review_note if lead else None,
            reviewed_at=lead.reviewed_at if lead else None,
            shortlisted_at=lead.shortlisted_at if lead else None,
            contacted_at=lead.last_contacted_at if lead else None,
            outreach_lead_id=result.outreach_lead_id,
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    def _lead_read(
        self,
        result: AudienceResultModel,
        *,
        audience: TerritoryModel | None = None,
        business: BusinessModel | None = None,
        lead: LeadModel | None = None,
        suppressions: list[ContactSuppressionModel] | None = None,
        preloaded: bool = False,
    ) -> AudienceLeadRead:
        audience = audience or self._audience(result.audience_id)
        snapshot = result.match_snapshot or {}
        raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
        profile_match = raw.get("profile_match") if isinstance(raw.get("profile_match"), dict) else {}
        matched_signals = profile_match.get("matched_signals") or []
        reasons = [
            reason
            for item in matched_signals
            if isinstance(item, dict)
            if (reason := _signal_reason(item)) is not None
        ]
        score = min(100, 80 + max(0, int(profile_match.get("confirmed_signal_count") or 0) - 1) * 5)
        contact_email = _optional_string(snapshot.get("contact_email"))
        if not preloaded:
            business = self.session.get(BusinessModel, result.business_id)
        attributes = _snapshot_attributes(raw)
        if not preloaded:
            lead = (
                self.session.get(LeadModel, result.outreach_lead_id)
                if result.outreach_lead_id
                else None
            )
        identifiers = self._suppression_identifiers(result, business=business)
        if suppressions is None:
            suppression = ContactSuppressionRepository(self.session).find_match(
                product_id=audience.product_id,
                workspace_id=audience.workspace_id,
                identifiers=identifiers,
            )
        else:
            identifier_set = set(identifiers)
            suppression = next(
                (
                    candidate
                    for candidate in suppressions
                    if (candidate.kind, candidate.value) in identifier_set
                ),
                None,
            )
        return AudienceLeadRead(
            id=result.id,
            campaign_id=(lead.campaign_id if lead and lead.campaign_id else audience.id),
            territory_id=audience.id,
            product_id=audience.product_id,
            business_id=result.business_id,
            audience_result_id=result.id,
            outreach_lead_id=result.outreach_lead_id,
            contact_id=lead.contact_id if lead else None,
            company_name=str(snapshot.get("title") or (business.name if business else "Unnamed business")),
            website_url=_optional_string(snapshot.get("url") or (business.website_url if business else None)),
            contact_email=lead.contact_email if lead else contact_email,
            contact_phone=_optional_string(business.phone) if business else None,
            google_rating=_optional_float(attributes.get("google_rating")),
            google_review_count=_optional_int(attributes.get("google_review_count")),
            geography=_optional_string(snapshot.get("geography")),
            description=_optional_string(snapshot.get("snippet")),
            source=str(snapshot.get("source") or "business_index"),
            raw_sources=[raw] if raw else [],
            review_status=LeadReviewStatus(lead.review_status) if lead else LeadReviewStatus.UNREVIEWED,
            review_note=lead.review_note if lead else None,
            reviewed_at=lead.reviewed_at if lead else None,
            shortlisted_at=lead.shortlisted_at if lead else None,
            contact_policy_status=suppression.status if suppression else "allowed",
            contact_policy_reason=suppression.reason if suppression else None,
            contact_policy_checked_at=suppression.updated_at if suppression else None,
            last_contacted_at=lead.last_contacted_at if lead else None,
            verification_status=lead.verification_status if lead else ("unknown" if contact_email else "unverified"),
            verification_provider=lead.verification_provider if lead else None,
            verification_checked_at=lead.verification_checked_at if lead else None,
            verification_reason=lead.verification_reason if lead else None,
            verification_score=lead.verification_score if lead else None,
            verification_details=lead.verification_details if lead else None,
            qualification=lead.qualification if lead else {
                "qualified": True,
                "fit_status": "good_fit",
                "score": score,
                "rationale": reasons[0] if reasons else "Matched the saved-search criteria.",
                "positive_signals": reasons,
                "signal_tags": [str(item.get("signal_key")) for item in matched_signals if isinstance(item, dict) and item.get("signal_key")],
                "recommended_next_step": "Review the evidence before outreach.",
            },
            latest_outcome=lead.latest_outcome if lead else None,
            latest_outcome_at=lead.latest_outcome_at if lead else None,
            approach=lead.approach if lead else None,
            outcome_adjustment=float(profile_match.get("outcome_adjustment") or 0.0),
            rank_score=float(score),
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    def _suppression_identifiers(
        self,
        result: AudienceResultModel,
        *,
        business: BusinessModel | None = None,
    ) -> list[tuple[str, str]]:
        snapshot = result.match_snapshot or {}
        if business is None:
            business = self.session.get(BusinessModel, result.business_id)
        identifiers: set[tuple[str, str]] = {("business_id", result.business_id)}
        email = normalize_email(str(snapshot.get("contact_email") or ""))
        if email:
            identifiers.add(("email", email))
        domain = normalize_domain(str(snapshot.get("url") or (business.website_url if business else "") or ""))
        if domain:
            identifiers.add(("domain", domain))
        phone = normalize_phone(business.phone if business else None)
        if phone:
            identifiers.add(("phone", phone))
        return sorted(identifiers)


def _business_id(row: dict) -> str:
    return str(row["raw"]["canonical_business_id"])


def _territory_niches(session: Session, territory: TerritoryModel) -> list[NicheModel]:
    primary = session.get(NicheModel, territory.niche_id)
    return [primary] if primary is not None and primary.active else []


def _optional_string(value) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _snapshot_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    attributes = raw.get("business_attributes")
    return attributes if isinstance(attributes, dict) else {}


def _optional_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value) -> int | None:
    number = _optional_float(value)
    return int(number) if number is not None else None


def _signal_reason(signal: dict) -> str | None:
    key = str(signal.get("signal_key") or "")
    value = signal.get("value")
    if key == "website_unavailable":
        return "No owned website was found."
    if key == "reviews_under_15":
        return f"The business has {int(value or 0)} public reviews."
    if key in {
        "no_quote_flow",
        "no_contact_form",
        "quote_or_booking_form_present",
        "contact_form_present",
        "primary_cta_present",
        "click_to_call_present",
    }:
        return None
    if key == "website_quality_score":
        return f"The measured website quality score is {value}."
    return f"Matched {key.replace('_', ' ')}."
