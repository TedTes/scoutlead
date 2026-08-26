from __future__ import annotations

import re

from agent_runs.schemas import AgentRunCreate
from agent_runs.service import AgentRunService
from campaigns.schemas import CampaignCreate, CampaignGoalType
from campaigns.service import CampaignService
from products.discovery_policy import validate_google_places_query
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ValidationError
from shared.utils import truncate, utcnow
from source_requests.schemas import (
    GOOGLE_PLACES_PROVIDER_ID,
    SourceRequestAction,
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
        apify_source_provider_id: str = "apify_actor",
    ) -> None:
        self.products = products
        self.campaigns = campaigns
        self.agent_runs = agent_runs
        self.apify_source_provider_id = apify_source_provider_id

    def plan(self, request: SourceRequestCreate) -> SourceRequestPlan:
        self.products.get(request.product_id)
        source = request.source.strip()
        query = _prompt_to_source_query(request.prompt)
        if source == GOOGLE_PLACES_PROVIDER_ID:
            validate_google_places_query(query)
            return SourceRequestPlan(
                source=source,
                action=SourceRequestAction.LIST_CONTACTS,
                query=query,
                max_results=request.max_results,
                source_preset_id="google-places-local-business",
                explanation=(
                    "List contacts by running a precise local-business source adapter. "
                    "No outreach drafts are created for source requests."
                ),
            )
        if source == self.apify_source_provider_id:
            return SourceRequestPlan(
                source=source,
                action=SourceRequestAction.LIST_CONTACTS,
                query=query,
                max_results=request.max_results,
                source_preset_id="apify-actor-source",
                explanation=(
                    "List contacts by running the configured Apify actor source adapter. "
                    "No outreach drafts are created for source requests."
                ),
            )
        supported_sources = [GOOGLE_PLACES_PROVIDER_ID]
        if self.apify_source_provider_id:
            supported_sources.append(self.apify_source_provider_id)
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
            else self.apify_source_provider_id
        )
        run = self.campaigns.create(
            CampaignCreate(
                product_id=product.id,
                name=f"{product.product_name} source request {utcnow().strftime('%Y-%m-%d %H:%M')}",
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


def _prompt_to_source_query(prompt: str) -> str:
    value = " ".join(prompt.strip().split())
    value = re.sub(
        r"\b(list|find|fetch|get|show|collect|pull|search|lookup|give me)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b(contacts?|leads?|businesses?|providers?|companies?|from|using|source|selected source|google places|google maps)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", " ", value).strip(" ,.-")
    if not value:
        raise ValidationError(
            "source request prompt is missing a searchable category and market",
            {
                "required_shape": (
                    "Use a request such as 'List painting service contacts in Toronto ON'."
                )
            },
        )
    return truncate(value, 180)
