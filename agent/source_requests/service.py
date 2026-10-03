from __future__ import annotations

from datetime import timedelta
from typing import Any

from business_index.repository import BusinessIndexRepository
from business_index.contracts import compile_search_contract, search_contract_hash
from business_index.schemas import BusinessIndexSearch, OpportunityType, SearchContract
from business_facts.repository import BusinessFactKey
from business_index.search import BusinessIndexSearchService
from campaign_sources.schemas import CampaignSourceSlot
from campaigns.schemas import (
    CampaignCreate,
    CampaignGoalType,
    CampaignRead,
    CampaignStatus,
)
from campaigns.service import CampaignService
from job_queue.service import QueueService
from products.repository import ProductRepository
from products.schemas import ProductRead
from run_diagnostics.repository import RunPipelineEventRepository
from shared.errors import ValidationError
from shared.utils import utcnow
from source_requests.compiler import SourceRequestCompiler
from source_requests.intent import (
    SearchIntentInterpreter,
    normalize_search_intent,
    search_intent_request_hash,
)
from source_requests.schemas import (
    AUTO_PROVIDER_ID,
    GOOGLE_PLACES_PROVIDER_ID,
    SourceRequestCreate,
    SourceRequestPlan,
    SourceRequestRun,
    SourceRequestIntent,
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
        del agent_runs
        self.llm = llm or campaigns.llm
        self.intent_interpreter = SearchIntentInterpreter(self.llm)
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
        return self._prepare(request)[4]

    def _compile_plan(
        self,
        request: SourceRequestCreate,
        *,
        product: ProductRead,
        intent: SourceRequestIntent,
        website_policy: str,
    ) -> SourceRequestPlan:
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
                intent=intent,
                website_policy=website_policy,
            )
        if source == GOOGLE_PLACES_PROVIDER_ID:
            return self.compiler.compile_google_places(
                request=request,
                product=product,
                intent=intent,
                website_policy=website_policy,
            )
        source_config = self.apify_sources.get(source)
        if source_config is not None:
            return self.compiler.compile_apify_source(
                request=request,
                product=product,
                source_config=source_config,
                intent=intent,
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
        (
            product,
            intent,
            search_contract,
            contract_hash,
            plan,
            intent_request_hash,
        ) = self._prepare(request)
        opportunity_type = _opportunity_type(search_contract)
        requires_digital_opportunity = opportunity_type != OpportunityType.ANY
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
                    "search_intent": intent.model_dump(mode="json"),
                    "search_intent_request_hash": intent_request_hash,
                    "search_contract_hash": contract_hash,
                    "requested_result_count": plan.max_results,
                    "business_index_segment_id": segment.id,
                    "business_index_contract": {
                        "niche_id": segment.niche_id,
                        "market_key": segment.market_key,
                        "opportunity_type": opportunity_type.value,
                        "evidence_max_age_days": request.evidence_max_age_days,
                        "result_count": plan.max_results,
                        "search_contract": search_contract.as_dict(),
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
                contract_hash=contract_hash,
                interpreted_intent=intent,
                unsupported_criteria=list(search_contract.unsupported),
                unresolved_criteria=[],
            )

        evidence_fresh_after = utcnow() - timedelta(days=request.evidence_max_age_days)
        matches, index_decisions = BusinessIndexSearchService(
            self.products.session
        ).search_with_diagnostics(
            BusinessIndexSearch(
                niche_id=segment.niche_id,
                market_key=segment.market_key,
                opportunity_type=opportunity_type,
                evidence_fresh_after=evidence_fresh_after,
                result_count=plan.max_results,
                contract=search_contract,
                contract_hash=contract_hash,
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
                "opportunity_type": opportunity_type.value,
                "evidence_max_age_days": request.evidence_max_age_days,
                "result_count": plan.max_results,
                "search_contract": search_contract.as_dict(),
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
                    "opportunity_type": opportunity_type.value,
                    "evidence_max_age_days": request.evidence_max_age_days,
                },
                response_payload=decision,
                reason=str(decision["reason"]),
            )
            if decision["status"] == "pending":
                QueueService(self.products.session).enqueue_business_search_evaluation(
                    business_id=str(decision["business_id"]),
                    contract_hash=contract_hash,
                    contract=search_contract.as_dict(),
                    campaign_id=run.id,
                    evidence_fresh_after=evidence_fresh_after.isoformat(),
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
            contract_hash=contract_hash,
            interpreted_intent=intent,
            unsupported_criteria=list(search_contract.unsupported),
            unresolved_criteria=_unresolved_criteria(
                index_decisions,
                search_contract=search_contract,
                has_matches=bool(current_count),
            ),
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
            intent_override=(
                SourceRequestIntent.model_validate(source_inputs["search_intent"])
                if isinstance(source_inputs.get("search_intent"), dict)
                else None
            ),
        )

    def _prepare(self, request: SourceRequestCreate):
        product = ProductRead.model_validate(self.products.get(request.product_id))
        intent_request_hash = search_intent_request_hash(request)
        intent = self._resolve_intent(
            request,
            product=product,
            request_hash=intent_request_hash,
        )
        search_contract = compile_search_contract(intent)
        contract_hash = search_contract_hash(
            intent,
            search_contract,
            evidence_max_age_days=request.evidence_max_age_days,
        )
        website_policy = _website_policy(search_contract)
        plan = self._compile_plan(
            request,
            product=product,
            intent=intent,
            website_policy=website_policy,
        )
        return (
            product,
            intent,
            search_contract,
            contract_hash,
            plan,
            intent_request_hash,
        )

    def _resolve_intent(
        self,
        request: SourceRequestCreate,
        *,
        product: ProductRead,
        request_hash: str,
    ) -> SourceRequestIntent:
        if request.intent_override is not None:
            return normalize_search_intent(
                request.intent_override,
                explicit_category=request.business_category,
                explicit_geography=request.geography,
            )
        for campaign in self.campaigns.campaigns.list_by_product(product.id):
            source_inputs = campaign.source_inputs or {}
            if source_inputs.get("search_intent_request_hash") != request_hash:
                continue
            saved = source_inputs.get("search_intent")
            if isinstance(saved, dict):
                return normalize_search_intent(SourceRequestIntent.model_validate(saved))
        return self.intent_interpreter.interpret(request=request, product=product)

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


def _unresolved_criteria(
    decisions: list[dict],
    *,
    search_contract: SearchContract,
    has_matches: bool,
) -> list[str]:
    unresolved: set[str] = set()
    marker = "Current facts are unavailable for: "
    for decision in decisions:
        reason = str(decision.get("reason") or "")
        if decision.get("status") == "pending":
            unresolved.update(search_contract.semantic_all_of)
            unresolved.update(search_contract.semantic_any_of)
            unresolved.update(search_contract.semantic_exclusions)
        if marker not in reason:
            continue
        values = reason.split(marker, 1)[1].rstrip(".")
        unresolved.update(item.strip() for item in values.split(",") if item.strip())
    if not decisions and not has_matches:
        unresolved.update(
            predicate.key
            for predicate in (*search_contract.all_of, *search_contract.any_of)
        )
    return sorted(unresolved)


def _opportunity_type(contract: SearchContract) -> OpportunityType:
    website_values: set[str] = set()
    conversion_gap = False
    for predicate in (*contract.all_of, *contract.any_of):
        if predicate.key == BusinessFactKey.WEBSITE_STATUS.value:
            values = predicate.value if isinstance(predicate.value, tuple) else (predicate.value,)
            website_values.update(str(value) for value in values)
        if predicate.key in {
            BusinessFactKey.QUOTE_OR_BOOKING_FORM_PRESENT.value,
            BusinessFactKey.CONTACT_FORM_PRESENT.value,
        } and predicate.value is False:
            conversion_gap = True
    if conversion_gap:
        return OpportunityType.WEAK_OR_MISSING_WEBSITE
    if website_values == {"missing"}:
        return OpportunityType.MISSING_WEBSITE
    if website_values and website_values <= {"missing", "not_listed", "unavailable", "parked"}:
        return OpportunityType.MISSING_OR_UNAVAILABLE_WEBSITE
    return OpportunityType.ANY


def _website_policy(contract: SearchContract) -> str:
    opportunity_type = _opportunity_type(contract)
    if opportunity_type == OpportunityType.MISSING_WEBSITE:
        return "missing"
    if opportunity_type == OpportunityType.MISSING_OR_UNAVAILABLE_WEBSITE:
        return "missing_or_unavailable"
    if opportunity_type == OpportunityType.WEAK_OR_MISSING_WEBSITE:
        return "weak_or_missing"
    return "any"
