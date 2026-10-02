from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from business_index.refresh import (
    BusinessIndexRefreshService,
    _assessment_needs_review,
    _campaign_source,
    _canonical_contact_email,
    _canonical_website_url,
    _indexed_row,
    _opportunity_policy,
    _source_external_id,
    _source_state_key,
)
from business_index.repository import BusinessIndexRepository
from campaigns.service import CampaignService
from canonical.repository import CanonicalRepository
from db.models import (
    BusinessFactModel,
    QueueJobModel,
    SourceItemModel,
    SourceObservationModel,
)
from discovery.classifier import assess_discovery_candidate
from evaluation.digital_opportunity import opportunity_evidence_from_sources
from job_queue.schemas import JobStatus, JobType
from job_queue.service import QueueService
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.utils import utcnow
from source_items.repository import SourceItemRepository
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemStage,
    SourceItemState,
)
from business_facts.repository import BusinessFactRepository, fact_value
from source_requests.schemas import SourceTask
from territories.opportunity_audit import BusinessOpportunityAuditor
from tools.search import SearchResult
from tools.source_registry import SourceAdapterRegistry


class BusinessIndexPipelineService:
    """Durable, independently retryable stages for scheduled index refreshes."""

    def __init__(
        self,
        *,
        session: Session,
        registry: SourceAdapterRegistry,
        campaigns: CampaignService,
        auditor: BusinessOpportunityAuditor,
        embedding: EmbeddingClient,
        discovery_config: dict[str, Any] | None = None,
    ) -> None:
        self.session = session
        self.registry = registry
        self.campaigns = campaigns
        self.auditor = auditor
        self.embedding = embedding
        self.segments = BusinessIndexRepository(session)
        self.items = SourceItemRepository(session)
        self.queue = QueueService(session)
        self.refresh_planner = BusinessIndexRefreshService(
            session=session,
            registry=registry,
            campaigns=campaigns,
            auditor=auditor,
            embedding=embedding,
            discovery_config=discovery_config,
        )

    def plan_refresh(self, segment_id: str) -> dict[str, Any]:
        segment = self._segment(segment_id)
        product = ProductRead.model_validate(
            ProductRepository(self.session).get(segment.product_id)
        )
        self.refresh_planner.rebuild_source_plan(segment, product)
        # Prevent the scheduler from repeatedly planning the same in-flight refresh.
        segment.last_refresh_at = utcnow()
        segment.next_refresh_at = utcnow() + timedelta(hours=6)
        self.session.commit()
        jobs = [
            self.queue.enqueue_source_fetch(
                segment_id=segment.id,
                source_index=index,
                task=task_data,
            )
            for index, task_data in enumerate(segment.source_plan or [])
        ]
        audit_jobs = [
            self.queue.enqueue_business_opportunity_audit(
                source_item_id=None,
                segment_id=segment.id,
                business_id=business_id,
            )
            for business_id in self._businesses_needing_fact_audit(segment)
        ]
        if not jobs and not audit_jobs:
            self.segments.complete_refresh(segment, succeeded=False)
        return {
            "segment_id": segment.id,
            "source_job_count": len(jobs),
            "fact_audit_job_count": len(audit_jobs),
        }

    def fetch_source(
        self,
        segment_id: str,
        *,
        source_index: int,
        task_data: dict[str, Any],
        job_id: str,
    ) -> dict[str, Any]:
        segment = self._segment(segment_id)
        product = ProductRead.model_validate(
            ProductRepository(self.session).get(segment.product_id)
        )
        task = SourceTask.model_validate(task_data)
        state_key = _source_state_key(task, source_index)
        attempted_at = utcnow()
        previous_state = (segment.source_state or {}).get(state_key) or {}
        source = _campaign_source(
            task,
            f"scheduled:{segment.id}",
            attempted_at,
            continuation_cursor=previous_state.get("cursor"),
        )
        result = self.registry.run(
            source,
            {
                "product": product.model_dump(mode="json"),
                "campaign": self.refresh_planner._scheduled_campaign(
                    segment, product
                ).model_dump(mode="json"),
            },
        )
        rows = list(result.data or [])[: task.max_results]
        source_items: list[SourceItemModel] = []
        for row in rows:
            normalized = _indexed_row(
                row,
                task=task,
                segment_id=segment.id,
                niche_id=segment.niche_id,
                market_label=segment.market_label,
                fetched_at=attempted_at,
            )
            search_result = SearchResult.model_validate(normalized)
            item = self.items.ingest(
                SourceItemCreate(
                    segment_id=segment.id,
                    job_id=job_id,
                    provider_id=task.provider_id,
                    external_id=_source_external_id(search_result),
                    query=task.query,
                    source_url=search_result.url,
                    title=search_result.title,
                    raw_payload=search_result.model_dump(mode="json"),
                    fetched_at=attempted_at,
                ),
                commit=False,
            )
            self._carry_forward_human_decision(item)
            source_items.append(item)
        self.session.commit()
        queued = 0
        for item in source_items:
            latest_decision = item.decisions[-1] if item.decisions else None
            if (
                latest_decision is not None
                and (
                    latest_decision.actor_type == "user"
                    or bool((latest_decision.details or {}).get("prior_user_decision_id"))
                )
                and latest_decision.decision in {
                    SourceItemDecisionValue.REJECTED.value,
                    SourceItemDecisionValue.DUPLICATE.value,
                }
            ):
                continue
            if item.business_id:
                self.queue.enqueue_business_opportunity_audit(
                    source_item_id=item.id,
                    segment_id=segment.id,
                    business_id=item.business_id,
                )
                queued += 1
            elif item.state == SourceItemState.RELEVANT.value:
                self.queue.enqueue_business_identity_resolve(
                    source_item_id=item.id,
                    segment_id=segment.id,
                )
                queued += 1
            elif item.state in {
                SourceItemState.FETCHED.value,
                SourceItemState.FAILED.value,
                SourceItemState.REJECTED.value,
                SourceItemState.NEEDS_REVIEW.value,
                SourceItemState.EXCLUDED.value,
            }:
                self.queue.enqueue_source_item_classify(
                    source_item_id=item.id,
                    segment_id=segment.id,
                )
                queued += 1
        self.segments.record_source_result(
            segment,
            provider_id=state_key,
            state={
                "provider_id": task.provider_id,
                "query": task.query,
                "quota": task.max_results,
                "fetched_count": len(rows),
                "persisted_count": len(source_items),
                "cost_usd": result.cost_usd,
                "cursor": (result.raw or {}).get("next_page_token"),
                "last_attempt_at": attempted_at.isoformat(),
                "last_success_at": utcnow().isoformat(),
                "failure": None,
            },
        )
        if not queued:
            self._maybe_complete(segment, current_job_id=job_id)
        return {"fetched_count": len(rows), "processing_job_count": queued}

    def classify_source_item(self, source_item_id: str, *, job_id: str) -> dict[str, Any]:
        item = self.items.get(source_item_id)
        segment = self._segment(item.segment_id)
        product = ProductRead.model_validate(
            ProductRepository(self.session).get(segment.product_id)
        )
        result = SearchResult.model_validate(item.raw_payload)
        assessment = assess_discovery_candidate(result, product)
        if not assessment.is_promotable:
            reviewable = _assessment_needs_review(
                assessment.candidate_type,
                assessment.confidence,
                item.provider_id,
            )
            self.items.add_decision(
                item.id,
                SourceItemDecisionCreate(
                    stage=SourceItemStage.RELEVANCE,
                    decision=(
                        SourceItemDecisionValue.NEEDS_REVIEW
                        if reviewable
                        else SourceItemDecisionValue.REJECTED
                    ),
                    reason=assessment.rejection_reason,
                    confidence=assessment.confidence,
                    details={"candidate_type": assessment.candidate_type.value},
                ),
                next_state=(
                    SourceItemState.NEEDS_REVIEW if reviewable else SourceItemState.REJECTED
                ),
            )
            self._maybe_complete(segment, current_job_id=job_id)
            return {"state": "needs_review" if reviewable else "rejected"}
        self.items.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.RELEVANCE,
                decision=SourceItemDecisionValue.ACCEPTED,
                reason="Source item has sufficient evidence of a target business.",
                confidence=assessment.confidence,
                details={"candidate_type": assessment.candidate_type.value},
            ),
            next_state=SourceItemState.RELEVANT,
        )
        self.queue.enqueue_business_identity_resolve(
            source_item_id=item.id,
            segment_id=segment.id,
        )
        return {"state": "relevant"}

    def _carry_forward_human_decision(self, item: SourceItemModel) -> None:
        previous = self.items.latest_user_decision_for(item)
        if previous is None:
            return
        decision = SourceItemDecisionValue(previous.decision)
        state = {
            SourceItemDecisionValue.ACCEPTED: SourceItemState.RELEVANT,
            SourceItemDecisionValue.REJECTED: SourceItemState.REJECTED,
            SourceItemDecisionValue.DUPLICATE: SourceItemState.EXCLUDED,
        }[decision]
        self.items.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.RELEVANCE,
                decision=decision,
                reason=f"Applied prior human decision: {previous.reason or decision.value}.",
                actor_type="system",
                details={"prior_user_decision_id": previous.id},
            ),
            next_state=state,
            commit=False,
        )

    def resolve_identity(self, source_item_id: str) -> dict[str, Any]:
        item = self.items.get(source_item_id)
        result = SearchResult.model_validate(item.raw_payload)
        raw = {**(result.raw or {}), "source_item_id": item.id}
        canonical = CanonicalRepository(self.session, embedding=self.embedding)
        link = canonical.upsert_from_discovery_result(
            company_name=result.title,
            website_url=_canonical_website_url(result.url, provider_id=item.provider_id),
            contact_email=_canonical_contact_email(
                result.contact_email,
                provider_id=item.provider_id,
            ),
            geography=result.geography,
            description=result.snippet,
            source=item.provider_id,
            raw=raw,
            allow_raw_contact_email=False,
        )
        if not link.business_id:
            raise RuntimeError(f"source item did not resolve to a business: {item.id}")
        self.items.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.IDENTITY,
                decision=SourceItemDecisionValue.RESOLVED,
                reason="Resolved to a canonical business.",
                details={"business_id": link.business_id},
            ),
            next_state=SourceItemState.AUDIT_PENDING,
            business_id=link.business_id,
        )
        self.queue.enqueue_business_opportunity_audit(
            source_item_id=item.id,
            segment_id=item.segment_id,
            business_id=link.business_id,
        )
        return {"business_id": link.business_id}

    def audit_opportunity(
        self,
        source_item_id: str | None,
        *,
        business_id: str,
        segment_id: str | None = None,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        item = self.items.get(source_item_id) if source_item_id else None
        resolved_segment_id = item.segment_id if item else segment_id
        if not resolved_segment_id:
            raise ValueError("segment_id is required when auditing without a source item")
        segment = self._segment(resolved_segment_id)
        self.auditor.audit_businesses(
            [business_id],
            category=segment.niche.category if segment.niche else None,
            market=segment.market_label,
            opportunity_policy=_opportunity_policy(segment.source_plan),
        )
        opportunity_evidence = None
        observations = self.session.scalars(
            select(SourceObservationModel)
            .where(SourceObservationModel.business_id == business_id)
            .order_by(SourceObservationModel.observed_at.desc())
        )
        for observation in observations:
            opportunity_evidence = opportunity_evidence_from_sources(
                [observation.raw_payload]
            )
            if opportunity_evidence is not None:
                break
        if item is not None:
            self.items.add_decision(
                item.id,
                SourceItemDecisionCreate(
                    stage=SourceItemStage.OPPORTUNITY,
                    decision=SourceItemDecisionValue.AUDITED,
                    reason="Opportunity audit completed; eligibility is evaluated separately.",
                    details={
                        "business_id": business_id,
                        "opportunity_evidence": opportunity_evidence,
                        "business_facts": {
                            key: fact_value(fact)
                            for key, fact in BusinessFactRepository(self.session)
                            .map_for_businesses([business_id])
                            .get(business_id, {})
                            .items()
                        },
                    },
                ),
                next_state=SourceItemState.AUDITED,
                business_id=business_id,
            )
        if job_id:
            self._maybe_complete(segment, current_job_id=job_id)
        return {"business_id": business_id, "state": "audited"}

    def _businesses_needing_fact_audit(self, segment) -> list[str]:
        business_ids = self.segments.business_ids(segment)
        if not business_ids:
            return []
        freshness_cutoff = utcnow() - timedelta(days=30)
        current = {
            row.business_id: row
            for row in self.session.scalars(
                select(BusinessFactModel).where(
                    BusinessFactModel.business_id.in_(business_ids),
                    BusinessFactModel.fact_key == "website_status",
                )
            )
        }
        candidates = [
            business_id
            for business_id in business_ids
            if business_id not in current
            or _aware(current[business_id].observed_at) < _aware(freshness_cutoff)
            or current[business_id].value_text in {"unknown", "not_listed"}
        ]
        limit = min(max(int(segment.target_business_count or 25), 1), 100)
        return candidates[:limit]

    def match_eligibility(self, segment_id: str, *, job_id: str) -> dict[str, Any]:
        """Complete legacy queued jobs; eligibility now belongs to a search contract."""
        segment = self._segment(segment_id)
        self._maybe_complete(segment, current_job_id=job_id)
        return {
            "evaluated_count": 0,
            "updated_item_count": 0,
            "deprecated": True,
        }

    def _segment(self, segment_id: str):
        segment = self.segments.get(segment_id)
        if segment is None:
            raise ValueError(f"business index segment not found: {segment_id}")
        return segment

    def _maybe_complete(self, segment, *, current_job_id: str) -> bool:
        stage_types = {
            JobType.SOURCE_FETCH.value,
            JobType.SOURCE_ITEM_CLASSIFY.value,
            JobType.BUSINESS_IDENTITY_RESOLVE.value,
            JobType.BUSINESS_OPPORTUNITY_AUDIT.value,
            JobType.SEARCH_ELIGIBILITY_MATCH.value,
        }
        active = list(
            self.session.scalars(
                select(QueueJobModel).where(
                    QueueJobModel.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                    QueueJobModel.type.in_(stage_types),
                    QueueJobModel.id != current_job_id,
                )
            )
        )
        if any(str(job.payload.get("segment_id")) == segment.id for job in active):
            return False
        succeeded = any(
            isinstance(state, dict) and state.get("last_success_at")
            for state in (segment.source_state or {}).values()
        )
        self.segments.complete_refresh(segment, succeeded=succeeded)
        return True


def _aware(value):
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
