from __future__ import annotations

from datetime import timedelta
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
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from campaigns.service import CampaignService
from canonical.repository import CanonicalRepository
from db.models import QueueJobModel, SourceItemModel, SourceObservationModel
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
        if not jobs:
            self.segments.complete_refresh(segment, succeeded=False)
        return {"segment_id": segment.id, "source_job_count": len(jobs)}

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
            source_items.append(item)
        self.session.commit()
        queued = 0
        for item in source_items:
            if item.state in {SourceItemState.FETCHED.value, SourceItemState.FAILED.value}:
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
        return {"fetched_count": len(rows), "classification_job_count": queued}

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
        source_item_id: str,
        *,
        business_id: str,
    ) -> dict[str, Any]:
        item = self.items.get(source_item_id)
        segment = self._segment(item.segment_id)
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
        self.items.add_decision(
            item.id,
            SourceItemDecisionCreate(
                stage=SourceItemStage.OPPORTUNITY,
                decision=SourceItemDecisionValue.AUDITED,
                reason="Opportunity audit completed; eligibility is evaluated separately.",
                details={
                    "business_id": business_id,
                    "opportunity_evidence": opportunity_evidence,
                },
            ),
            next_state=SourceItemState.AUDITED,
            business_id=business_id,
        )
        self.queue.enqueue_search_eligibility_match(segment_id=segment.id)
        return {"business_id": business_id, "state": "audited"}

    def match_eligibility(self, segment_id: str, *, job_id: str) -> dict[str, Any]:
        segment = self._segment(segment_id)
        _, decisions = BusinessIndexSearchService(self.session).search_with_diagnostics(
            BusinessIndexSearch(
                niche_id=segment.niche_id,
                market_key=segment.market_key,
                opportunity_type=OpportunityType.ANY,
                evidence_fresh_after=utcnow() - timedelta(days=30),
                result_count=max(segment.target_business_count, 25),
            )
        )
        items_by_business: dict[str, list[SourceItemModel]] = {}
        for item in self.items.list_for_segment(segment.id, limit=2000):
            if item.business_id:
                items_by_business.setdefault(item.business_id, []).append(item)
        updated = 0
        for decision in decisions:
            business_id = str(decision["business_id"])
            outside_limit = "outside the requested result limit" in str(decision["reason"])
            for item in items_by_business.get(business_id, []):
                if item.state not in {
                    SourceItemState.AUDITED.value,
                    SourceItemState.AUDIT_PENDING.value,
                }:
                    continue
                if decision["status"] == "accepted":
                    value = SourceItemDecisionValue.ELIGIBLE
                    state = SourceItemState.ELIGIBLE
                elif outside_limit:
                    continue
                else:
                    value = SourceItemDecisionValue.EXCLUDED
                    state = SourceItemState.EXCLUDED
                self.items.add_decision(
                    item.id,
                    SourceItemDecisionCreate(
                        stage=SourceItemStage.ELIGIBILITY,
                        decision=value,
                        reason=str(decision["reason"]),
                        details=decision,
                    ),
                    next_state=state,
                    commit=False,
                )
                updated += 1
        self.session.commit()
        self._maybe_complete(segment, current_job_id=job_id)
        return {"evaluated_count": len(decisions), "updated_item_count": updated}

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
