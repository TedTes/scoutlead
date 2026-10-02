from __future__ import annotations

from datetime import timedelta
from typing import Any

from business_index.repository import BusinessIndexRepository
from business_index.schemas import BusinessIndexSearch, OpportunityType
from business_index.search import BusinessIndexSearchService
from campaign_sources.schemas import CampaignSourceSlot
from campaigns.schemas import (
    CampaignCreate,
    CampaignGoalType,
    CampaignRead,
    CampaignStatus,
)
from campaigns.service import CampaignService
from evaluation.digital_opportunity import (
    product_requires_digital_opportunity,
    text_requires_digital_opportunity,
)
from products.repository import ProductRepository
from products.schemas import ProductRead
from run_diagnostics.repository import RunPipelineEventRepository
from shared.errors import ValidationError
from shared.utils import utcnow
from source_requests.compiler import SourceRequestCompiler
from source_requests.schemas import (
    AUTO_PROVIDER_ID,
    GOOGLE_PLACES_PROVIDER_ID,
    SourceRequestCreate,
    SourceRequestPlan,
    SourceRequestRun,
)


class SourceRequestService:
    def __init__(
        self,
        *,
        products: ProductRepository,
        campaigns: CampaignService,
        agent_runs: Any | None = None,
        llm: Any | None = None,
        apify_source_provider_id: str = "apify_actor",
        apify_source_label: str = "Kijiji",
        apify_sources: list[dict[str, Any]] | None = None,
        google_places_configured: bool | None = None,
        search_configured: bool | None = None,
        openstreetmap_enabled: bool = True,
        source_recipes: list[dict[str, Any]] | None = None,
    ) -> None:
        self.products = products
        self.campaigns = campaigns
        del agent_runs, llm
        self.compiler = SourceRequestCompiler()
        self.apify_source_provider_id = apify_source_provider_id
        self.apify_source_label = apify_source_label
        self.google_places_configured = (
            bool(campaigns.google_places_api_key)
            if google_places_configured is None
            else google_places_configured
        )
        self.search_configured = (
            campaigns.search_tool.is_configured
            if search_configured is None
            else search_configured
        )
        self.openstreetmap_enabled = openstreetmap_enabled
        self.source_recipes = source_recipes or []
        self.apify_sources = self._apify_source_map(
            apify_sources=apify_sources,
            fallback_provider_id=apify_source_provider_id,
            fallback_label=apify_source_label,
        )

    def plan(self, request: SourceRequestCreate) -> SourceRequestPlan:
        product = ProductRead.model_validate(self.products.get(request.product_id))
        source = request.source.strip()
        if source == AUTO_PROVIDER_ID:
            return self.compiler.compile_auto(
                request=request,
                product=product,
                google_places_configured=self.google_places_configured,
                search_configured=self.search_configured,
                openstreetmap_enabled=self.openstreetmap_enabled,
                apify_sources=[
                    config
                    for config in self.apify_sources.values()
                    if _apify_source_is_configured(config)
                ],
                source_recipes=self.source_recipes,
            )
        if source == GOOGLE_PLACES_PROVIDER_ID:
            return self.compiler.compile_google_places(request=request, product=product)
        source_config = self.apify_sources.get(source)
        if source_config is not None:
            return self.compiler.compile_apify_source(
                request=request,
                product=product,
                source_config=source_config,
            )
        supported_sources = [
            AUTO_PROVIDER_ID,
            GOOGLE_PLACES_PROVIDER_ID,
            *self.apify_sources.keys(),
        ]
        raise ValidationError(
            "source provider is not configured",
            {"source": source, "supported_sources": supported_sources},
        )

    def create(self, request: SourceRequestCreate) -> SourceRequestRun:
        plan = self.plan(request)
        product = ProductRead.model_validate(self.products.get(request.product_id))
        requires_digital_opportunity = (
            product_requires_digital_opportunity(product)
            or text_requires_digital_opportunity(request.prompt)
        )
        intent = plan.intent
        if intent is None:
            raise ValidationError("source request could not be interpreted")
        segment = BusinessIndexRepository(self.products.session).resolve_or_create_segment(
            product_id=product.id,
            business_category=intent.business_category,
            market_label=intent.location or intent.country,
            source_plan=[task.model_dump(mode="json") for task in plan.tasks],
            target_business_count=plan.max_results,
        )
        source_selection = (
            "google_places_local_business"
            if plan.source == GOOGLE_PLACES_PROVIDER_ID
            else plan.source
        )
        run = self.campaigns.create(
            CampaignCreate(
                product_id=product.id,
                name=_source_request_run_name(plan=plan, request=request),
                goal_type=CampaignGoalType.LEARN,
                source_preset_id=plan.source_preset_id,
                source_input=plan.query,
                source_inputs={
                    "source_request_prompt": request.prompt,
                    "source_request_action": plan.action.value,
                    "source_request_source": plan.source,
                    "source_provider_id": plan.source,
                    "source_selection": source_selection,
                    "source_selection_reason": plan.explanation,
                    "source_request_intent": (
                        plan.intent.model_dump(mode="json") if plan.intent else None
                    ),
                    "requested_result_count": plan.max_results,
                    "business_index_segment_id": segment.id,
                    "business_index_contract": {
                        "niche_id": segment.niche_id,
                        "market_key": segment.market_key,
                        "opportunity_type": _opportunity_type(request, plan).value,
                        "evidence_max_age_days": request.evidence_max_age_days,
                        "result_count": plan.max_results,
                    },
                    "requires_digital_opportunity": requires_digital_opportunity,
                    **plan.source_inputs,
                },
                max_leads=plan.max_results,
                channels=["manual"],
            )
        )
        pipeline_events = RunPipelineEventRepository(self.products.session)
        pipeline_events.create(
            campaign_id=run.id,
            segment_id=segment.id,
            stage="request",
            event_type="request_created",
            status="completed",
            request_payload=request.model_dump(mode="json"),
            response_payload={
                "source": plan.source,
                "query": plan.query,
                "intent": plan.intent.model_dump(mode="json") if plan.intent else None,
                "task_count": len(plan.tasks),
                "tasks": [
                    {
                        "provider_id": task.provider_id,
                        "query": task.query,
                        "quota": task.max_results,
                        "reason": task.reason,
                    }
                    for task in plan.tasks
                ],
                "segment_id": segment.id,
            },
        )
        if not request.run_immediately:
            return SourceRequestRun(
                plan=plan,
                run=run,
                summary=None,
                state="ready",
                current_result_count=0,
                requested_result_count=plan.max_results,
            )

        matches, index_decisions = BusinessIndexSearchService(
            self.products.session
        ).search_with_diagnostics(
            BusinessIndexSearch(
                niche_id=segment.niche_id,
                market_key=segment.market_key,
                opportunity_type=_opportunity_type(request, plan),
                evidence_fresh_after=utcnow()
                - timedelta(days=request.evidence_max_age_days),
                result_count=plan.max_results,
            )
        )
        self.campaigns.materialize_existing_matches(run.id, matches)
        current_count = len(self.campaigns.results(run.id))
        deficit = max(0, plan.max_results - current_count)
        pipeline_events.create(
            campaign_id=run.id,
            segment_id=segment.id,
            stage="index_match",
            event_type="index_query",
            status="completed",
            request_payload={
                "niche_id": segment.niche_id,
                "market_key": segment.market_key,
                "opportunity_type": _opportunity_type(request, plan).value,
                "evidence_max_age_days": request.evidence_max_age_days,
                "result_count": plan.max_results,
            },
            response_payload={
                "match_count": current_count,
                "deficit": deficit,
                "business_ids": [
                    business_id
                    for match in matches
                    if (business_id := _match_business_id(match))
                ],
            },
        )
        for decision in index_decisions:
            pipeline_events.create(
                campaign_id=run.id,
                segment_id=segment.id,
                stage="index_match",
                event_type="index_decision",
                status=str(decision["status"]),
                business_id=str(decision["business_id"]),
                item_key=str(decision.get("company_name") or decision["business_id"]),
                request_payload={
                    "opportunity_type": _opportunity_type(request, plan).value,
                    "evidence_max_age_days": request.evidence_max_age_days,
                },
                response_payload=decision,
                reason=str(decision["reason"]),
            )
        if deficit and plan.tasks:
            pipeline_events.create(
                campaign_id=run.id,
                segment_id=segment.id,
                stage="index_demand",
                event_type="coverage_requested",
                status="recorded",
                request_payload={
                    "niche_id": segment.niche_id,
                    "market_key": segment.market_key,
                    "requested_count": plan.max_results,
                },
                response_payload={
                    "current_count": current_count,
                    "deficit": deficit,
                    "segment_id": segment.id,
                    "next_refresh_at": (
                        segment.next_refresh_at.isoformat() if segment.next_refresh_at else None
                    ),
                },
                reason="Unmet demand was recorded for scheduled business-index refresh.",
            )
        run = self.campaigns.campaigns.update_status(run.id, CampaignStatus.COMPLETED)
        pipeline_events.create(
            campaign_id=run.id,
            segment_id=segment.id,
            stage="final_output",
            event_type="output_snapshot",
            status="completed",
            response_payload={
                "result_count": current_count,
                "lead_ids": [result.id for result in self.campaigns.results(run.id)],
            },
        )
        return SourceRequestRun(
            plan=plan,
            run=CampaignRead.model_validate(run),
            summary=None,
            state="ready",
            current_result_count=current_count,
            requested_result_count=plan.max_results,
        )

    def rerun(self, run_id: str, *, run_immediately: bool = True) -> SourceRequestRun:
        run = CampaignRead.model_validate(self.campaigns.get(run_id))
        return self.create(self._rerun_request(run, run_immediately=run_immediately))

    def _rerun_request(self, run: CampaignRead, *, run_immediately: bool) -> SourceRequestCreate:
        source_inputs = run.source_inputs or {}
        saved_intent = source_inputs.get("source_request_intent")
        saved_intent = saved_intent if isinstance(saved_intent, dict) else {}
        index_contract = source_inputs.get("business_index_contract")
        index_contract = index_contract if isinstance(index_contract, dict) else {}
        source = _string_value(
            source_inputs.get("source_request_source")
            or source_inputs.get("source_provider_id")
        )
        prompt = _string_value(source_inputs.get("source_request_prompt"))

        if not source or not prompt:
            sources = self.campaigns.campaign_sources.list_by_campaign(
                run.id,
                slot=CampaignSourceSlot.DISCOVERY,
                enabled_only=True,
            )
            if sources:
                first_source = sources[0]
                source = source or first_source.provider_id
                prompt = prompt or _string_value(
                    first_source.input.get("source_request_prompt")
                    or first_source.input.get("query")
                )

        prompt = prompt or _string_value(run.source_input)
        if not source:
            raise ValidationError(
                "run cannot be rerun without a saved source",
                {
                    "run_id": run.id,
                    "user_message": "This run does not have a saved source to re-run.",
                },
            )
        if not prompt:
            raise ValidationError(
                "run cannot be rerun without a saved search prompt",
                {
                    "run_id": run.id,
                    "user_message": "This run does not have a saved search prompt to re-run.",
                },
            )

        return SourceRequestCreate(
            product_id=run.product_id,
            source=source,
            prompt=prompt,
            name=run.name,
            max_results=(
                _positive_int(source_inputs.get("requested_result_count"))
                or run.max_leads
            ),
            run_immediately=run_immediately,
            business_category=_string_value(saved_intent.get("business_category")) or None,
            geography=_string_value(
                saved_intent.get("location") or saved_intent.get("country")
            )
            or None,
            opportunity_type=_string_value(index_contract.get("opportunity_type")) or None,
            evidence_max_age_days=(
                _positive_int(index_contract.get("evidence_max_age_days")) or 30
            ),
        )

    @staticmethod
    def _apify_source_map(
        *,
        apify_sources: list[dict[str, Any]] | None,
        fallback_provider_id: str,
        fallback_label: str,
    ) -> dict[str, dict[str, Any]]:
        source_configs = apify_sources
        if source_configs is None:
            source_configs = [{"id": fallback_provider_id, "label": fallback_label}]
        mapped: dict[str, dict[str, Any]] = {}
        for source_config in source_configs:
            source_id = str(
                source_config.get("id")
                or source_config.get("provider_id")
                or source_config.get("source_provider_id")
                or ""
            ).strip()
            if source_id:
                mapped[source_id] = source_config
        return mapped


def _source_request_run_name(
    *,
    plan: SourceRequestPlan,
    request: SourceRequestCreate,
) -> str:
    if request.name and request.name.strip():
        return _truncate_name(request.name)

    if plan.intent:
        category = _title_text(plan.intent.business_category)
        location = _title_text(plan.intent.location or plan.intent.country)
        if category and location:
            return _truncate_name(f"{category} · {location}")
        if category:
            return _truncate_name(category)

    prompt = request.prompt.strip()
    if prompt:
        return _truncate_name(prompt)
    return f"Contact list {utcnow().strftime('%Y-%m-%d %H:%M')}"


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _title_text(value: str) -> str:
    words = value.replace("_", " ").replace("-", " ").split()
    return " ".join(word if word.isupper() else word.capitalize() for word in words)


def _truncate_name(value: str, max_length: int = 64) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 1].rstrip()}…"


def _apify_source_is_configured(source: dict[str, Any]) -> bool:
    return bool(
        source.get("api_token")
        and source.get("actor_id")
        and (
            source.get("input_template")
            or source.get("search_url_template")
            or source.get("input_kind")
        )
    )


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _match_business_id(match: Any) -> str | None:
    raw = match.get("raw") if isinstance(match, dict) else getattr(match, "raw", None)
    if not isinstance(raw, dict):
        return None
    value = raw.get("canonical_business_id")
    return str(value) if value else None


def _opportunity_type(
    request: SourceRequestCreate,
    plan: SourceRequestPlan,
) -> OpportunityType:
    explicit = _string_value(request.opportunity_type)
    if explicit:
        try:
            return OpportunityType(explicit)
        except ValueError as exc:
            raise ValidationError(
                "unsupported opportunity type",
                {
                    "opportunity_type": explicit,
                    "supported": [item.value for item in OpportunityType],
                },
            ) from exc
    website_policy = _string_value(plan.source_inputs.get("website_policy"))
    if website_policy == "missing":
        return OpportunityType.MISSING_WEBSITE
    if website_policy == "missing_or_unavailable":
        return OpportunityType.MISSING_OR_UNAVAILABLE_WEBSITE
    return OpportunityType.ANY
