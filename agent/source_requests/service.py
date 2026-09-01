from __future__ import annotations

from typing import Any

from agent_runs.schemas import AgentRunCreate
from agent_runs.service import AgentRunService
from agents.llm import LLMClient
from campaign_sources.schemas import CampaignSourceSlot
from campaigns.schemas import CampaignCreate, CampaignGoalType, CampaignRead
from campaigns.service import CampaignService
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ValidationError
from shared.utils import utcnow
from source_requests.compiler import SourceRequestCompiler
from source_requests.schemas import (
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
        agent_runs: AgentRunService,
        llm: LLMClient,
        apify_source_provider_id: str = "apify_actor",
        apify_source_label: str = "Kijiji",
        apify_sources: list[dict[str, Any]] | None = None,
    ) -> None:
        self.products = products
        self.campaigns = campaigns
        self.agent_runs = agent_runs
        self.compiler = SourceRequestCompiler(llm=llm)
        self.apify_source_provider_id = apify_source_provider_id
        self.apify_source_label = apify_source_label
        self.apify_sources = self._apify_source_map(
            apify_sources=apify_sources,
            fallback_provider_id=apify_source_provider_id,
            fallback_label=apify_source_label,
        )

    def plan(self, request: SourceRequestCreate) -> SourceRequestPlan:
        product = ProductRead.model_validate(self.products.get(request.product_id))
        source = request.source.strip()
        if source == GOOGLE_PLACES_PROVIDER_ID:
            return self.compiler.compile_google_places(request=request, product=product)
        source_config = self.apify_sources.get(source)
        if source_config is not None:
            return self.compiler.compile_apify_source(
                request=request,
                product=product,
                source_config=source_config,
            )
        supported_sources = [GOOGLE_PLACES_PROVIDER_ID, *self.apify_sources.keys()]
        raise ValidationError(
            "source provider is not configured",
            {"source": source, "supported_sources": supported_sources},
        )

    def create(self, request: SourceRequestCreate) -> SourceRequestRun:
        plan = self.plan(request)
        product = ProductRead.model_validate(self.products.get(request.product_id))
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
                    **plan.source_inputs,
                },
                max_leads=plan.max_results,
                channels=["manual"],
            )
        )
        if not request.run_immediately:
            return SourceRequestRun(plan=plan, run=run, summary=None)

        agent_run = self.agent_runs.create(AgentRunCreate(campaign_id=run.id))
        summary = self.campaigns.run_contact_listing(run.id, agent_run_id=agent_run.id)
        return SourceRequestRun(plan=plan, run=summary.campaign, summary=summary)

    def rerun(self, run_id: str, *, run_immediately: bool = True) -> SourceRequestRun:
        run = CampaignRead.model_validate(self.campaigns.get(run_id))
        return self.create(self._rerun_request(run, run_immediately=run_immediately))

    def _rerun_request(self, run: CampaignRead, *, run_immediately: bool) -> SourceRequestCreate:
        source_inputs = run.source_inputs or {}
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
            max_results=run.max_leads,
            run_immediately=run_immediately,
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
