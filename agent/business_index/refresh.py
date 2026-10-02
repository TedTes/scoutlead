from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient
from business_index.repository import BusinessIndexRepository
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from campaign_sources.schemas import (
    CampaignSourceMode,
    CampaignSourceRead,
    CampaignSourceSlot,
)
from campaigns.schemas import CampaignRead, CampaignStage, CampaignStatus
from campaigns.service import CampaignService
from canonical.repository import CanonicalRepository
from canonical.website_enrichment import SOURCE_NAME as WEBSITE_AUDIT_SOURCE
from db.models import BusinessModel, CampaignModel, SourceObservationModel
from discovery.classifier import assess_discovery_candidate
from discovery.schemas import DiscoveryCandidateType
from products.repository import ProductRepository
from products.schemas import ProductRead
from run_diagnostics.repository import RunPipelineEventRepository
from shared.utils import new_id, utcnow
from source_items.repository import SourceItemRepository
from source_items.schemas import (
    SourceItemCreate,
    SourceItemDecisionCreate,
    SourceItemDecisionValue,
    SourceItemStage,
    SourceItemState,
)
from source_requests.schemas import SourceTask
from source_requests.compiler import SourceRequestCompiler
from source_requests.schemas import SourceRequestCreate
from territories.opportunity_audit import (
    WEBSITE_PRESENCE_SOURCE,
    BusinessOpportunityAuditor,
)
from tools.search import SearchResult
from tools.source_registry import SourceAdapterRegistry


class BusinessIndexRefreshService:
    """Expand durable business coverage outside the API request path."""

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
        self.discovery_config = discovery_config
        self.segments = BusinessIndexRepository(session)

    def refresh(self, segment_id: str, *, job_id: str | None = None) -> dict[str, Any]:
        segment = self.segments.get(segment_id)
        if segment is None:
            raise ValueError(f"business index segment not found: {segment_id}")
        product = ProductRead.model_validate(
            ProductRepository(self.session).get(segment.product_id)
        )
        self.rebuild_source_plan(segment, product)
        campaigns = self._expanding_campaigns(segment.id)
        pipeline_events = RunPipelineEventRepository(self.session)
        source_items = SourceItemRepository(self.session)
        context_campaign = campaigns[0] if campaigns else self._scheduled_campaign(segment, product)
        canonical = CanonicalRepository(self.session, embedding=self.embedding)
        existing_business_ids = self.segments.business_ids(segment)
        provider_business_ids: list[list[str]] = []
        successful_sources = 0

        for index, task_data in enumerate(segment.source_plan or []):
            task = SourceTask.model_validate(task_data)
            state_key = _source_state_key(task, index)
            attempted_at = utcnow()
            try:
                previous_state = (segment.source_state or {}).get(state_key) or {}
                source = _campaign_source(
                    task,
                    context_campaign.id,
                    attempted_at,
                    continuation_cursor=previous_state.get("cursor"),
                )
                result = self.registry.run(
                    source,
                    {
                        "product": product.model_dump(mode="json"),
                        "campaign": context_campaign.model_dump(mode="json"),
                    },
                )
                rows = list(result.data or [])[: task.max_results]
                self._record_pipeline_events(
                    pipeline_events,
                    campaigns,
                    segment_id=segment.id,
                    job_id=job_id,
                    stage="source_fetch",
                    event_type="provider_fetch",
                    status="completed",
                    provider_id=task.provider_id,
                    request_payload=_safe_task_request(task),
                    response_payload={
                        "fetched_count": len(rows),
                        "cost_usd": result.cost_usd,
                        "has_next_cursor": bool((result.raw or {}).get("next_page_token")),
                    },
                    commit=False,
                )
                persisted_rows = []
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
                    source_item = source_items.ingest(
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
                    normalized["raw"]["source_item_id"] = source_item.id
                    persisted_rows.append((source_item, normalized, search_result))
                # Preserve provider output even when a later judgment stage fails.
                self.session.commit()

                written = 0
                source_business_ids: list[str] = []
                for source_item, normalized, search_result in persisted_rows:
                    assessment = assess_discovery_candidate(search_result, product)
                    if not assessment.is_promotable:
                        reviewable = _assessment_needs_review(
                            assessment.candidate_type,
                            assessment.confidence,
                            task.provider_id,
                        )
                        source_items.add_decision(
                            source_item.id,
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
                                SourceItemState.NEEDS_REVIEW
                                if reviewable
                                else SourceItemState.REJECTED
                            ),
                            commit=False,
                        )
                        self._record_pipeline_events(
                            pipeline_events,
                            campaigns,
                            segment_id=segment.id,
                            job_id=job_id,
                            stage="candidate_filter",
                            event_type="candidate_decision",
                            status="rejected",
                            provider_id=task.provider_id,
                            item_key=search_result.url or search_result.title,
                            request_payload={"query": task.query},
                            response_payload=search_result.model_dump(mode="json"),
                            reason=assessment.rejection_reason
                            or f"Classified as {assessment.candidate_type.value} ({assessment.confidence} confidence).",
                            commit=False,
                        )
                        continue
                    source_items.add_decision(
                        source_item.id,
                        SourceItemDecisionCreate(
                            stage=SourceItemStage.RELEVANCE,
                            decision=SourceItemDecisionValue.ACCEPTED,
                            reason="Source item has sufficient evidence of a target business.",
                            confidence=assessment.confidence,
                            details={"candidate_type": assessment.candidate_type.value},
                        ),
                        next_state=SourceItemState.RELEVANT,
                        commit=False,
                    )
                    link = canonical.upsert_from_discovery_result(
                        company_name=search_result.title,
                        website_url=_canonical_website_url(
                            search_result.url,
                            provider_id=task.provider_id,
                        ),
                        contact_email=_canonical_contact_email(
                            search_result.contact_email,
                            provider_id=task.provider_id,
                        ),
                        geography=search_result.geography,
                        description=search_result.snippet,
                        source=task.provider_id,
                        raw=normalized["raw"],
                        allow_raw_contact_email=False,
                    )
                    if link.business_id:
                        source_items.add_decision(
                            source_item.id,
                            SourceItemDecisionCreate(
                                stage=SourceItemStage.IDENTITY,
                                decision=SourceItemDecisionValue.RESOLVED,
                                reason="Resolved to a canonical business.",
                                details={"business_id": link.business_id},
                            ),
                            next_state=SourceItemState.AUDIT_PENDING,
                            business_id=link.business_id,
                            commit=False,
                        )
                        source_business_ids.append(link.business_id)
                        written += 1
                        self._record_pipeline_events(
                            pipeline_events,
                            campaigns,
                            segment_id=segment.id,
                            job_id=job_id,
                            stage="candidate_filter",
                            event_type="candidate_decision",
                            status="accepted",
                            provider_id=task.provider_id,
                            business_id=link.business_id,
                            item_key=search_result.url or search_result.title,
                            request_payload={"query": task.query},
                            response_payload={
                                **search_result.model_dump(mode="json"),
                                "candidate_type": assessment.candidate_type.value,
                                "confidence": assessment.confidence,
                            },
                            reason="Written to the canonical business index.",
                            commit=False,
                        )
                self.session.commit()
                provider_business_ids.append(source_business_ids)
                successful_sources += 1
                self.segments.record_source_result(
                    segment,
                    provider_id=state_key,
                    state={
                        "provider_id": task.provider_id,
                        "query": task.query,
                        "quota": task.max_results,
                        "fetched_count": len(rows),
                        "written_count": written,
                        "cost_usd": result.cost_usd,
                        "cursor": (result.raw or {}).get("next_page_token"),
                        "last_attempt_at": attempted_at.isoformat(),
                        "last_success_at": utcnow().isoformat(),
                        "failure": None,
                    },
                )
            except Exception as exc:
                self.session.rollback()
                self._record_pipeline_events(
                    pipeline_events,
                    campaigns,
                    segment_id=segment.id,
                    job_id=job_id,
                    stage="source_fetch",
                    event_type="provider_fetch",
                    status="failed",
                    provider_id=task.provider_id,
                    request_payload=_safe_task_request(task),
                    reason=str(exc),
                )
                self.segments.record_source_result(
                    segment,
                    provider_id=state_key,
                    state={
                        "provider_id": task.provider_id,
                        "query": task.query,
                        "quota": task.max_results,
                        "fetched_count": 0,
                        "written_count": 0,
                        "last_attempt_at": attempted_at.isoformat(),
                        "failure": str(exc),
                    },
                )

        if segment.source_plan and successful_sources == 0:
            self.segments.complete_refresh(segment, succeeded=False)
            raise RuntimeError(f"all business index sources failed for segment {segment.id}")

        business_ids = _round_robin_unique(provider_business_ids, existing_business_ids)
        # Existing audited matches should become visible while fresh candidates are
        # inspected. The final pass below re-scores the same leads idempotently.
        self._fill_expanding_campaigns(segment.id, complete=False)
        audit_business_ids = self._audit_batch(segment, business_ids)
        if audit_business_ids:
            self.auditor.audit_businesses(
                audit_business_ids,
                category=segment.niche.category if segment.niche else None,
                market=segment.market_label,
                opportunity_policy=_opportunity_policy(segment.source_plan),
            )
        self._record_pipeline_events(
            pipeline_events,
            campaigns,
            segment_id=segment.id,
            job_id=job_id,
            stage="opportunity_audit",
            event_type="audit_batch",
            status="completed",
            response_payload={
                "candidate_count": len(business_ids),
                "audited_count": len(audit_business_ids),
                "business_ids": audit_business_ids,
            },
        )
        filled = self._fill_expanding_campaigns(
            segment.id,
            complete=True,
            pipeline_events=pipeline_events,
            job_id=job_id,
        )
        for campaign in campaigns:
            results = self.campaigns.results(campaign.id)
            pipeline_events.create(
                campaign_id=campaign.id,
                segment_id=segment.id,
                job_id=job_id,
                stage="final_output",
                event_type="output_snapshot",
                status="completed",
                response_payload={
                    "result_count": len(results),
                    "lead_ids": [result.id for result in results],
                },
            )
        self.segments.complete_refresh(segment, succeeded=successful_sources > 0)
        return {
            "segment_id": segment.id,
            "source_count": len(segment.source_plan or []),
            "successful_source_count": successful_sources,
            "business_count": len(business_ids),
            "audited_business_count": len(audit_business_ids),
            "filled_campaign_count": filled,
        }

    @staticmethod
    def _record_pipeline_events(
        repository: RunPipelineEventRepository,
        campaigns: list[CampaignRead],
        *,
        commit: bool = True,
        **values: Any,
    ) -> None:
        for campaign in campaigns:
            repository.create(campaign_id=campaign.id, commit=False, **values)
        if campaigns and commit:
            repository.session.commit()

    def rebuild_source_plan(self, segment, product: ProductRead) -> None:
        if self.discovery_config is None:
            return
        apify_sources = [
            source
            for source in self.discovery_config.get("apify_sources", [])
            if source.get("api_token")
            and source.get("actor_id")
            and (
                source.get("input_template")
                or source.get("search_url_template")
                or source.get("input_kind")
            )
        ]
        plan = SourceRequestCompiler().compile_auto(
            request=SourceRequestCreate(
                product_id=product.id,
                source="auto",
                prompt=f"{segment.niche.category} in {segment.market_label}",
                business_category=segment.niche.category or segment.niche.label,
                geography=segment.market_label,
                max_results=segment.target_business_count,
                run_immediately=False,
            ),
            product=product,
            google_places_configured=bool(
                self.discovery_config.get("google_places_configured")
            ),
            search_configured=bool(self.discovery_config.get("search_configured")),
            openstreetmap_enabled=bool(
                self.discovery_config.get("openstreetmap_enabled", True)
            ),
            apify_sources=apify_sources,
            source_recipes=list(self.discovery_config.get("source_recipes", [])),
        )
        segment.source_plan = [task.model_dump(mode="json") for task in plan.tasks]
        self.session.commit()

    def _expanding_campaigns(self, segment_id: str) -> list[CampaignRead]:
        rows = self.session.scalars(
            select(CampaignModel).where(CampaignModel.status == CampaignStatus.EXPANDING.value)
        )
        return [
            CampaignRead.model_validate(row)
            for row in rows
            if (row.source_inputs or {}).get("business_index_segment_id") == segment_id
        ]

    def _audit_batch(self, segment, business_ids: list[str]) -> list[str]:
        if not business_ids:
            return []
        businesses = {
            business.id: business
            for business in self.session.scalars(
                select(BusinessModel).where(BusinessModel.id.in_(business_ids))
            )
        }
        observations = list(
            self.session.scalars(
                select(SourceObservationModel).where(
                    SourceObservationModel.business_id.in_(business_ids),
                    SourceObservationModel.source.in_(
                        [
                            WEBSITE_AUDIT_SOURCE,
                            WEBSITE_PRESENCE_SOURCE,
                            "google_places",
                            "google_places_seed",
                        ]
                    ),
                )
                .order_by(SourceObservationModel.observed_at.desc())
            )
        )
        audited_ids = {
            observation.business_id
            for observation in observations
            if observation.source in {WEBSITE_AUDIT_SOURCE, WEBSITE_PRESENCE_SOURCE}
        }
        google_website_state: dict[str, bool] = {}
        for observation in observations:
            if observation.source not in {"google_places", "google_places_seed"}:
                continue
            google_website_state.setdefault(
                observation.business_id,
                _observation_has_website(observation.raw_payload),
            )
        google_missing_ids = {
            business_id
            for business_id, has_website in google_website_state.items()
            if not has_website
        }
        conflicting_website_ids = {
            business_id
            for business_id in google_missing_ids
            if businesses.get(business_id) is not None
            and bool(businesses[business_id].website_url)
        }
        positions = {business_id: index for index, business_id in enumerate(business_ids)}
        candidates = [
            business_id for business_id in business_ids if business_id in businesses
        ]
        candidates.sort(
            key=lambda business_id: _audit_candidate_priority(
                business_id,
                google_missing_ids=google_missing_ids,
                conflicting_website_ids=conflicting_website_ids,
                audited_ids=audited_ids,
                has_website=bool(businesses[business_id].website_url),
                position=positions[business_id],
            )
        )
        limit = min(max(int(segment.target_business_count or 25), 1), 25)
        return candidates[:limit]

    def _fill_expanding_campaigns(
        self,
        segment_id: str,
        *,
        complete: bool,
        pipeline_events: RunPipelineEventRepository | None = None,
        job_id: str | None = None,
    ) -> int:
        segment = self.segments.get(segment_id)
        if segment is None:
            return 0
        filled = 0
        for campaign in self._expanding_campaigns(segment_id):
            contract = (campaign.source_inputs or {}).get("business_index_contract") or {}
            try:
                opportunity_type = OpportunityType(
                    contract.get("opportunity_type") or OpportunityType.ANY.value
                )
            except ValueError:
                opportunity_type = OpportunityType.ANY
            max_age_days = int(contract.get("evidence_max_age_days") or 30)
            rows, decisions = BusinessIndexSearchService(
                self.session
            ).search_with_diagnostics(
                BusinessIndexSearch(
                    niche_id=segment.niche_id,
                    market_key=segment.market_key,
                    opportunity_type=opportunity_type,
                    evidence_fresh_after=utcnow() - timedelta(days=max_age_days),
                    result_count=campaign.max_leads,
                )
            )
            if complete and pipeline_events is not None:
                for decision in decisions:
                    pipeline_events.create(
                        campaign_id=campaign.id,
                        segment_id=segment.id,
                        job_id=job_id,
                        stage="index_match",
                        event_type="index_decision",
                        status=str(decision["status"]),
                        business_id=str(decision["business_id"]),
                        item_key=str(
                            decision.get("company_name") or decision["business_id"]
                        ),
                        request_payload={
                            "opportunity_type": opportunity_type.value,
                            "evidence_max_age_days": max_age_days,
                        },
                        response_payload=decision,
                        reason=str(decision["reason"]),
                        commit=False,
                    )
                self.session.commit()
            self.campaigns.materialize_existing_matches(campaign.id, rows)
            if complete:
                self.campaigns.campaigns.update_status(
                    campaign.id, CampaignStatus.COMPLETED
                )
            filled += 1
        return filled

    @staticmethod
    def _scheduled_campaign(segment, product: ProductRead) -> CampaignRead:
        now = utcnow()
        return CampaignRead(
            id=f"scheduled:{segment.id}",
            product_id=product.id,
            name=f"Refresh {segment.market_label}",
            goal_type="learn",
            source_input=f"{segment.niche.category} in {segment.market_label}",
            source_inputs={"requested_result_count": segment.target_business_count},
            max_leads=max(25, segment.target_business_count),
            channels=["manual"],
            status=CampaignStatus.DRAFT,
            stage=CampaignStage.DISCOVERY,
            created_at=now,
            updated_at=now,
        )


def _campaign_source(
    task: SourceTask,
    campaign_id: str,
    now: datetime,
    *,
    continuation_cursor: str | None = None,
) -> CampaignSourceRead:
    cursor_input = {"continuation_cursor": continuation_cursor} if continuation_cursor else {}
    return CampaignSourceRead(
        id=new_id("index_source"),
        campaign_id=campaign_id,
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id=task.provider_id,
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": task.query, **task.input, **cursor_input},
        config={"limit": task.max_results, "stage": task.stage, **task.config, **cursor_input},
        priority=task.priority,
        enabled=True,
        budget_limit=task.budget_limit,
        created_at=now,
        updated_at=now,
    )


def _safe_task_request(task: SourceTask) -> dict[str, Any]:
    return {
        "query": task.query,
        "provider_id": task.provider_id,
        "quota": task.max_results,
        "stage": task.stage,
        "priority": task.priority,
        "input": _redact_secrets(task.input),
        "config": _redact_secrets(task.config),
        "reason": task.reason,
    }


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if not isinstance(value, dict):
        return value
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        normalized = str(key).lower().replace("-", "_")
        is_secret = any(
            part in normalized
            for part in ("api_key", "token", "secret", "password", "authorization")
        )
        redacted[str(key)] = "[redacted]" if is_secret else _redact_secrets(item)
    return redacted


def _round_robin_unique(
    provider_business_ids: list[list[str]],
    remaining_business_ids: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    longest = max((len(items) for items in provider_business_ids), default=0)
    for index in range(longest):
        for items in provider_business_ids:
            if index >= len(items):
                continue
            business_id = items[index]
            if business_id not in seen:
                ordered.append(business_id)
                seen.add(business_id)
    for business_id in remaining_business_ids:
        if business_id not in seen:
            ordered.append(business_id)
            seen.add(business_id)
    return ordered


def _canonical_website_url(value: str | None, *, provider_id: str) -> str | None:
    if provider_id not in {"google_places", "openstreetmap"}:
        return None
    return value


def _canonical_contact_email(value: str | None, *, provider_id: str) -> str | None:
    if provider_id != "openstreetmap":
        return None
    return value


def _audit_candidate_priority(
    business_id: str,
    *,
    google_missing_ids: set[str],
    conflicting_website_ids: set[str],
    audited_ids: set[str],
    has_website: bool,
    position: int,
) -> tuple[bool, bool, bool, bool, int]:
    return (
        business_id not in conflicting_website_ids,
        business_id not in google_missing_ids,
        business_id in audited_ids,
        has_website,
        position,
    )


def _observation_has_website(raw: dict[str, Any]) -> bool:
    stack: list[object] = [raw]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"website_url", "websiteUri"} and isinstance(item, str):
                    if item.strip():
                        return True
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return False


def _indexed_row(
    row: dict[str, Any],
    *,
    task: SourceTask,
    segment_id: str,
    niche_id: str,
    market_label: str,
    fetched_at: datetime,
) -> dict[str, Any]:
    result = SearchResult.model_validate(row)
    raw = {
        **(result.raw or {}),
        "provider_id": task.provider_id,
        "query": task.query,
        "source_query": task.query,
        "source_url": (result.raw or {}).get("source_url") or result.url,
        "fetched_at": fetched_at.isoformat(),
        "provider_payload": result.model_dump(mode="json"),
        "business_index_segment_id": segment_id,
        "source_input": {
            "niche_id": niche_id,
            "business_category": task.input.get("business_category") or task.query,
            "location": task.input.get("location") or market_label,
            "query": task.query,
            "source_request_intent": {
                "niche_id": niche_id,
                "business_category": task.input.get("business_category") or task.query,
                "location": task.input.get("location") or market_label,
            },
        },
        "niche_id": niche_id,
    }
    return {**result.model_dump(mode="json"), "source": task.provider_id, "raw": raw}


def _source_state_key(task: SourceTask, index: int) -> str:
    recipe = str(task.input.get("source_recipe_id") or "").strip()
    return f"{task.provider_id}:{recipe or index}"


def _opportunity_policy(source_plan: list[dict[str, Any]]) -> str:
    for task in source_plan or []:
        config = task.get("config") if isinstance(task, dict) else None
        if isinstance(config, dict) and config.get("website_policy"):
            return str(config["website_policy"])
    return "any"


def _source_external_id(result: SearchResult) -> str | None:
    raw = result.raw or {}
    provider_payload = raw.get("provider_payload")
    payload_raw = provider_payload.get("raw") if isinstance(provider_payload, dict) else None
    candidates = (
        raw.get("external_id"),
        raw.get("place_id"),
        raw.get("placeId"),
        raw.get("id"),
        payload_raw.get("id") if isinstance(payload_raw, dict) else None,
        payload_raw.get("placeId") if isinstance(payload_raw, dict) else None,
        result.url,
    )
    for value in candidates:
        if value is not None and str(value).strip():
            return str(value).strip()[:500]
    return None


def _assessment_needs_review(
    candidate_type: DiscoveryCandidateType,
    confidence: int,
    provider_id: str,
) -> bool:
    if candidate_type == DiscoveryCandidateType.UNKNOWN and confidence >= 45:
        return True
    provider = provider_id.casefold()
    return candidate_type == DiscoveryCandidateType.VENDOR and any(
        marketplace in provider for marketplace in ("kijiji", "craigslist", "marketplace")
    )
