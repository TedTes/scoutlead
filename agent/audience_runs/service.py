from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from business_index.eligibility import searchable_business_conditions
from audience_runs.schemas import (
    AudienceLeadRead,
    AudienceResultRead,
    AudienceResultUpdate,
    AudienceRunRead,
    AudienceRunState,
)
from db.models import (
    AudienceResultModel,
    AudienceRunModel,
    BusinessFactModel,
    BusinessModel,
    BusinessNicheMembershipModel,
    CoverageRequestModel,
    LeadModel,
    NicheModel,
    SignalDefinitionModel,
    TerritoryModel,
)
from job_queue.service import QueueService
from seeding.batches import active_membership_condition
from shared.geospatial import haversine_distance_km_expression
from shared.errors import ConflictError, NotFoundError
from shared.utils import new_id, utcnow
from canonical.normalization import normalize_domain, normalize_email, normalize_phone
from leads.schemas import LeadContactPolicyUpdate, ContactPolicyStatus
from suppressions.repository import ContactSuppressionRepository
from territories.matching import ProfileMatchService


class AudienceRunService:
    def __init__(self, session: Session, *, workspace_id: str | None) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def create(
        self,
        audience_id: str,
        *,
        deadline_minutes: int = 10,
        commit: bool = True,
    ) -> AudienceRunModel:
        audience = self._audience(audience_id)
        active = self.session.scalar(
            select(AudienceRunModel)
            .where(
                AudienceRunModel.audience_id == audience.id,
                AudienceRunModel.criteria_version == audience.criteria_version,
                AudienceRunModel.state.in_(
                    [
                        AudienceRunState.QUEUED.value,
                        AudienceRunState.MATCHING.value,
                        AudienceRunState.WAITING_VALIDATION.value,
                    ]
                ),
            )
            .order_by(AudienceRunModel.created_at.desc())
            .limit(1)
        )
        if active is not None:
            return active
        now = utcnow()
        run = AudienceRunModel(
            id=new_id("audience_run"),
            workspace_id=self.workspace_id,
            audience_id=audience.id,
            criteria_version=audience.criteria_version,
            state=AudienceRunState.QUEUED.value,
            requested_count=audience.batch_size,
            result_count=0,
            new_result_count=0,
            deadline_at=now + timedelta(minutes=max(1, deadline_minutes)),
        )
        self.session.add(run)
        if commit:
            self.session.commit()
            self.session.refresh(run)
        else:
            self.session.flush()
        return run

    def process(self, run_id: str) -> tuple[AudienceRunModel, bool]:
        run = self._run(run_id)
        if run.state in {AudienceRunState.READY.value, AudienceRunState.PARTIAL.value}:
            return run, False
        audience = self._audience(run.audience_id)
        if run.criteria_version != audience.criteria_version:
            run.state = AudienceRunState.FAILED.value
            run.failure_reason = "Audience criteria changed after this run was queued."
            run.completed_at = utcnow()
            self.session.commit()
            return run, False
        now = utcnow()
        run.state = AudienceRunState.MATCHING.value
        run.started_at = run.started_at or now
        run.index_snapshot_at = now
        self.session.commit()
        niches = _territory_niches(self.session, audience)
        self._enqueue_staged_signal_collection(audience, niches)
        rows = ProfileMatchService(self.session).match(
            profile=audience,
            niche_ids=[niche.id for niche in niches],
            limit=min(max(run.requested_count * 8, 100), 500),
        )
        previously_delivered = set(
            self.session.scalars(
                select(AudienceResultModel.business_id)
                .where(
                    AudienceResultModel.audience_id == audience.id,
                    AudienceResultModel.run_id != run.id,
                )
            )
        )
        new_rows = [row for row in rows if _business_id(row) not in previously_delivered]
        older_rows = [row for row in rows if _business_id(row) in previously_delivered]
        selected = [*new_rows, *older_rows][: run.requested_count]
        existing_results = {
            result.business_id: result
            for result in self.session.scalars(
                select(AudienceResultModel).where(AudienceResultModel.run_id == run.id)
            )
        }
        for temporary_rank, result in enumerate(existing_results.values(), start=1):
            result.rank_position = -temporary_rank
        self.session.flush()
        selected_business_ids: set[str] = set()
        inserted_count = 0
        new_result_count = 0
        for row in selected:
            business_id = _business_id(row)
            selected_business_ids.add(business_id)
            inserted_count += 1
            if business_id not in previously_delivered:
                new_result_count += 1
            result = existing_results.get(business_id)
            if result is None:
                result = AudienceResultModel(
                    id=new_id("audience_result"),
                    run_id=run.id,
                    audience_id=audience.id,
                    business_id=business_id,
                    rank_position=inserted_count,
                    is_new=business_id not in previously_delivered,
                    match_snapshot=row,
                )
                self.session.add(result)
            else:
                result.rank_position = inserted_count
                result.is_new = business_id not in previously_delivered
                result.match_snapshot = row
        for business_id, result in existing_results.items():
            if business_id not in selected_business_ids:
                self.session.delete(result)
        run.result_count = inserted_count
        run.new_result_count = new_result_count
        needs_expansion = False
        if run.result_count >= run.requested_count:
            run.state = AudienceRunState.READY.value
            run.failure_reason = None
            run.completed_at = now
            audience.last_run_at = now
            self._complete_coverage(run.id)
        elif _before_deadline(now, run.deadline_at):
            self._request_coverage(run, audience, niches)
            if self._coverage_in_progress(run.id):
                run.state = AudienceRunState.WAITING_VALIDATION.value
                run.completed_at = None
                needs_expansion = self._queued_coverage_exists(run.id)
            else:
                run.state = AudienceRunState.PARTIAL.value
                run.completed_at = now
                audience.last_run_at = now
        else:
            run.state = AudienceRunState.PARTIAL.value
            run.completed_at = now
            audience.last_run_at = now
            self._complete_coverage(run.id)
        self.session.commit()
        self.session.refresh(run)
        return run, needs_expansion

    def _enqueue_staged_signal_collection(
        self,
        audience: TerritoryModel,
        niches: list[NicheModel],
    ) -> int:
        """Validate relevant staged facts already present when a run starts."""
        signal_keys = list(dict.fromkeys(audience.signal_keys or []))
        if (
            not signal_keys
            or not niches
            or audience.latitude is None
            or audience.longitude is None
        ):
            return 0
        distance_km = haversine_distance_km_expression(
            center_latitude=audience.latitude,
            center_longitude=audience.longitude,
            latitude=BusinessModel.latitude,
            longitude=BusinessModel.longitude,
        )
        statement = (
            select(SignalDefinitionModel, BusinessModel.id)
            .join(
                BusinessFactModel,
                BusinessFactModel.signal_definition_id == SignalDefinitionModel.id,
            )
            .join(BusinessModel, BusinessModel.id == BusinessFactModel.business_id)
            .join(
                BusinessNicheMembershipModel,
                BusinessNicheMembershipModel.business_id == BusinessModel.id,
            )
            .where(
                SignalDefinitionModel.key.in_(signal_keys),
                SignalDefinitionModel.status == "active",
                SignalDefinitionModel.collector_key.is_not(None),
                SignalDefinitionModel.opportunity_direction != "none",
                BusinessFactModel.quality_state == "staged",
                BusinessNicheMembershipModel.niche_id.in_(
                    [niche.id for niche in niches]
                ),
                active_membership_condition(),
                *searchable_business_conditions(),
                BusinessModel.latitude.is_not(None),
                BusinessModel.longitude.is_not(None),
                distance_km <= float(audience.radius_km),
            )
        )
        if audience.customer_kind != "both":
            statement = statement.where(
                or_(
                    BusinessModel.customer_kind == audience.customer_kind,
                    BusinessModel.customer_kind == "unknown",
                    BusinessModel.customer_kind.is_(None),
                )
            )
        by_definition: dict[str, tuple[SignalDefinitionModel, list[str]]] = {}
        for definition, business_id in self.session.execute(statement).unique():
            _, business_ids = by_definition.setdefault(
                definition.id,
                (definition, []),
            )
            if business_id not in business_ids:
                business_ids.append(business_id)

        queued = 0
        queue = QueueService(self.session)
        for definition, business_ids in by_definition.values():
            for batch_number, business_id in enumerate(business_ids, start=1):
                queue.enqueue_signal_collection(
                    signal_definition_id=definition.id,
                    signal_version=definition.version,
                    business_ids=[business_id],
                    requested_by=None,
                    reason="audience_staged_fact_validation",
                    batch_number=batch_number,
                    commit=False,
                )
                queued += 1
        return queued

    def get_read(self, run_id: str) -> AudienceRunRead:
        run = self._run(run_id)
        results = list(
            self.session.scalars(
                select(AudienceResultModel)
                .where(AudienceResultModel.run_id == run.id)
                .order_by(AudienceResultModel.rank_position)
            )
        )
        return AudienceRunRead.model_validate(run).model_copy(
            update={"results": [AudienceResultRead.model_validate(row) for row in results]}
        )

    def latest_for_audience(self, audience_id: str) -> AudienceRunRead | None:
        self._audience(audience_id)
        run = self.session.scalar(
            select(AudienceRunModel)
            .where(AudienceRunModel.audience_id == audience_id)
            .order_by(AudienceRunModel.created_at.desc())
            .limit(1)
        )
        return self.get_read(run.id) if run else None

    def latest_leads_for_audience(self, audience_id: str) -> list[AudienceLeadRead]:
        self._audience(audience_id)
        run = self.session.scalar(
            select(AudienceRunModel)
            .where(
                AudienceRunModel.audience_id == audience_id,
                AudienceRunModel.state.in_(
                    [
                        AudienceRunState.READY.value,
                        AudienceRunState.PARTIAL.value,
                        AudienceRunState.WAITING_VALIDATION.value,
                    ]
                ),
                select(AudienceResultModel.id)
                .where(AudienceResultModel.run_id == AudienceRunModel.id)
                .exists(),
            )
            .order_by(AudienceRunModel.created_at.desc())
            .limit(1)
        )
        if run is None:
            return []
        return [
            self._lead_read(result)
            for result in self.session.scalars(
                select(AudienceResultModel)
                .where(AudienceResultModel.run_id == run.id)
                .order_by(AudienceResultModel.rank_position)
            )
        ]

    def update_result(
        self,
        result_id: str,
        update: AudienceResultUpdate,
    ) -> AudienceLeadRead:
        result = self._result(result_id)
        now = utcnow()
        values = update.model_dump(exclude_unset=True)
        if "review_status" in values:
            review_status = values["review_status"]
            result.review_status = str(
                review_status.value if hasattr(review_status, "value") else review_status
            )
            result.reviewed_at = now
            if result.review_status == "not_fit":
                result.shortlisted_at = None
        if "review_note" in values:
            result.review_note = values["review_note"]
        if "shortlisted" in values:
            if values["shortlisted"]:
                audience = self._audience(result.audience_id)
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
                            "user_message": (
                                "This business is marked do-not-contact and cannot "
                                "be shortlisted."
                            ),
                        },
                    )
            if values["shortlisted"] and result.review_status == "not_fit":
                result.review_status = "maybe"
                result.reviewed_at = now
            result.shortlisted_at = now if values["shortlisted"] else None
        self.session.commit()
        self.session.refresh(result)
        from territories.refill import enqueue_refill_if_depleted

        enqueue_refill_if_depleted(self.session, result.audience_id)
        return self._lead_read(result)

    def update_contact_policy(
        self,
        result_id: str,
        update: LeadContactPolicyUpdate,
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
            result.shortlisted_at = None
            self.session.commit()
        return self._lead_read(result)

    def _request_coverage(self, run, audience, niches) -> bool:
        created = False
        deficit = max(0, run.requested_count - run.result_count)
        for niche in niches:
            existing = self.session.scalar(
                select(CoverageRequestModel)
                .where(
                    CoverageRequestModel.run_id == run.id,
                    CoverageRequestModel.niche_id == niche.id,
                )
                .limit(1)
            )
            if existing is not None:
                continue
            self.session.add(
                CoverageRequestModel(
                    id=new_id("coverage"),
                    run_id=run.id,
                    audience_id=audience.id,
                    niche_id=niche.id,
                    market_key=audience.market_key,
                    requested_count=deficit,
                    status="queued",
                )
            )
            created = True
        return created

    def _complete_coverage(self, run_id: str) -> None:
        for request in self.session.scalars(
            select(CoverageRequestModel).where(CoverageRequestModel.run_id == run_id)
        ):
            if request.status == "failed":
                continue
            request.status = "completed"
            request.completed_at = utcnow()

    def _coverage_in_progress(self, run_id: str) -> bool:
        return (
            self.session.scalar(
                select(CoverageRequestModel.id)
                .where(
                    CoverageRequestModel.run_id == run_id,
                    CoverageRequestModel.status.in_(["queued", "processing"]),
                )
                .limit(1)
            )
            is not None
        )

    def _queued_coverage_exists(self, run_id: str) -> bool:
        return (
            self.session.scalar(
                select(CoverageRequestModel.id)
                .where(
                    CoverageRequestModel.run_id == run_id,
                    CoverageRequestModel.status == "queued",
                )
                .limit(1)
            )
            is not None
        )

    def _audience(self, audience_id: str) -> TerritoryModel:
        audience = self.session.get(TerritoryModel, audience_id)
        if audience is None or (
            self.workspace_id is not None and audience.workspace_id != self.workspace_id
        ):
            raise NotFoundError("audience not found", {"audience_id": audience_id})
        return audience

    def _run(self, run_id: str) -> AudienceRunModel:
        run = self.session.get(AudienceRunModel, run_id)
        if run is None or (
            self.workspace_id is not None and run.workspace_id != self.workspace_id
        ):
            raise NotFoundError("audience run not found", {"run_id": run_id})
        return run

    def _result(self, result_id: str) -> AudienceResultModel:
        result = self.session.get(AudienceResultModel, result_id)
        if result is None:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        run = self._run(result.run_id)
        if run.audience_id != result.audience_id:
            raise NotFoundError("audience result not found", {"result_id": result_id})
        return result

    def _lead_read(self, result: AudienceResultModel) -> AudienceLeadRead:
        audience = self._audience(result.audience_id)
        snapshot = result.match_snapshot or {}
        raw = snapshot.get("raw") if isinstance(snapshot.get("raw"), dict) else {}
        profile_match = (
            raw.get("profile_match")
            if isinstance(raw.get("profile_match"), dict)
            else {}
        )
        matched_signals = profile_match.get("matched_signals") or []
        reasons = [
            _signal_reason(signal)
            for signal in matched_signals
            if isinstance(signal, dict)
        ]
        score = min(
            100,
            80 + max(0, int(profile_match.get("confirmed_signal_count") or 0) - 1) * 5,
        )
        contact_email = _optional_string(snapshot.get("contact_email"))
        business = self.session.get(BusinessModel, result.business_id)
        business_facts = (
            raw.get("business_facts")
            if isinstance(raw.get("business_facts"), dict)
            else {}
        )
        outreach_lead = (
            self.session.get(LeadModel, result.outreach_lead_id)
            if result.outreach_lead_id
            else None
        )
        suppression = ContactSuppressionRepository(self.session).find_match(
            product_id=audience.product_id,
            workspace_id=audience.workspace_id,
            identifiers=self._suppression_identifiers(result),
        )
        return AudienceLeadRead(
            id=result.id,
            campaign_id=result.run_id,
            territory_id=result.audience_id,
            product_id=audience.product_id,
            business_id=result.business_id,
            outreach_lead_id=result.outreach_lead_id,
            company_name=str(snapshot.get("title") or "Unnamed business"),
            website_url=_optional_string(snapshot.get("url")),
            contact_id=outreach_lead.contact_id if outreach_lead else None,
            contact_email=(
                outreach_lead.contact_email if outreach_lead else contact_email
            ),
            contact_phone=(
                _optional_string(business.phone) if business is not None else None
            ),
            google_rating=_optional_float(business_facts.get("google_rating")),
            google_review_count=_optional_int(
                business_facts.get("google_review_count")
            ),
            geography=_optional_string(snapshot.get("geography")),
            description=_optional_string(snapshot.get("snippet")),
            source=str(snapshot.get("source") or "business_index"),
            raw_sources=[raw] if raw else [],
            review_status=result.review_status,
            review_note=result.review_note,
            reviewed_at=result.reviewed_at,
            shortlisted_at=result.shortlisted_at,
            contact_policy_status=(
                suppression.status if suppression is not None else "allowed"
            ),
            contact_policy_reason=(
                suppression.reason if suppression is not None else None
            ),
            contact_policy_checked_at=(
                suppression.updated_at if suppression is not None else None
            ),
            last_contacted_at=(
                outreach_lead.last_contacted_at if outreach_lead else result.contacted_at
            ),
            verification_status=(
                outreach_lead.verification_status
                if outreach_lead
                else "unknown" if contact_email else "unverified"
            ),
            verification_provider=(
                outreach_lead.verification_provider if outreach_lead else None
            ),
            verification_checked_at=(
                outreach_lead.verification_checked_at if outreach_lead else None
            ),
            verification_reason=(
                outreach_lead.verification_reason if outreach_lead else None
            ),
            verification_score=(
                outreach_lead.verification_score if outreach_lead else None
            ),
            verification_details=(
                outreach_lead.verification_details if outreach_lead else None
            ),
            qualification=(outreach_lead.qualification if outreach_lead else {
                "qualified": True,
                "fit_status": "good_fit",
                "score": score,
                "score_breakdown": {
                    "fit_score": score,
                    "reachability_score": 40 if contact_email else 0,
                    "source_quality_score": 90,
                    "scoring_notes": [
                        "Matched against published business facts for this audience."
                    ],
                },
                "rationale": reasons[0] if reasons else "Matched the saved audience criteria.",
                "positive_signals": reasons,
                "signal_tags": [
                    str(signal.get("signal_key"))
                    for signal in matched_signals
                    if isinstance(signal, dict) and signal.get("signal_key")
                ],
                "missing_evidence": [],
                "risks": [],
                "criteria": [],
                "recommended_next_step": "Review the evidence before outreach.",
            }),
            latest_outcome=(outreach_lead.latest_outcome if outreach_lead else None),
            latest_outcome_at=(
                outreach_lead.latest_outcome_at if outreach_lead else None
            ),
            approach=(outreach_lead.approach if outreach_lead else None),
            outcome_adjustment=float(profile_match.get("outcome_adjustment") or 0.0),
            rank_score=float(score),
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    def _suppression_identifiers(
        self,
        result: AudienceResultModel,
    ) -> list[tuple[str, str]]:
        snapshot = result.match_snapshot or {}
        business = self.session.get(BusinessModel, result.business_id)
        identifiers: set[tuple[str, str]] = {
            ("business_id", result.business_id),
        }
        email = normalize_email(str(snapshot.get("contact_email") or ""))
        if email:
            identifiers.add(("email", email))
        domain = normalize_domain(
            str(snapshot.get("url") or (business.website_url if business else "") or "")
        )
        if domain:
            identifiers.add(("domain", domain))
        phone = normalize_phone(business.phone if business else None)
        if phone:
            identifiers.add(("phone", phone))
        return sorted(identifiers)


def _business_id(row: dict) -> str:
    return str(row["raw"]["canonical_business_id"])


def _before_deadline(now: datetime, deadline: datetime) -> bool:
    if deadline.tzinfo is None and now.tzinfo is not None:
        deadline = deadline.replace(tzinfo=now.tzinfo)
    return now < deadline


def _territory_niches(session: Session, territory: TerritoryModel) -> list[NicheModel]:
    primary = session.get(NicheModel, territory.niche_id)
    return [primary] if primary is not None and primary.active else []


def _optional_string(value) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


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


def _signal_reason(signal: dict) -> str:
    key = str(signal.get("signal_key") or "")
    value = signal.get("value")
    if key == "website_unavailable":
        return "The verified website status is unavailable."
    if key == "reviews_under_15":
        return f"The business has {int(value or 0)} public reviews."
    if key == "no_quote_flow":
        return "No quote or booking flow was found in the stored inspection."
    if key == "no_contact_form":
        return "No contact form was found in the stored inspection."
    return f"Matched {key.replace('_', ' ')}."
