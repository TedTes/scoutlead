from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent_runs.repository import AgentRunRepository
from agents.embeddings import EmbeddingClient, MissingEmbeddingClient
from agents.llm import LLMClient, MissingLLMClient
from agents.runner import ToolAction
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead, CampaignSourceSlot
from campaigns.repository import CampaignRepository
from campaigns.schemas import (
    CampaignCreate,
    CampaignPreflightCheck,
    CampaignPreflightRead,
    CampaignRead,
    CampaignRunSummary,
    CampaignStage,
    CampaignStatus,
    CampaignUpdate,
)
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead
from canonical.repository import CanonicalRepository
from db.models import CampaignModel
from discovery.repository import DiscoveryCandidateRepository
from discovery.classifier import assess_discovery_candidate
from discovery.schemas import DiscoveryCandidateCreate
from evaluation.campaign_metrics import calculate_campaign_metrics
from evaluation.schemas import CampaignMetrics
from icp.service import ICPPresetService
from leads.repository import LeadRepository
from leads.schemas import (
    AgentFitStatus,
    ContactVerificationStatus,
    CriterionScore,
    LeadFitType,
    LeadRead,
    LeadResearch,
    QualificationResult,
)
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from orchestration.hit_rate import calculate_hit_rates
from products.discovery_policy import validate_google_places_query
from products.repository import ProductRepository
from products.schemas import ProductRead
from shared.errors import ConflictError
from shared.utils import truncate
from source_presets.service import SourcePresetService
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.verify import EmailVerificationTool
from tools.search import SearchResult, SearchTool
from tools.source_registry import SourceAdapterRegistry
from workflows.discovery import DiscoveryWorkflow, _rows_with_semantic_context, _rows_with_source_context
from workflows.contact import ContactWorkflow
from workflows.outreach import OutreachWorkflow
from workflows.qualification import QualificationWorkflow
from workflows.research import ResearchWorkflow
from workflows.signal import SignalWorkflow
from workflows.verify import VerifyWorkflow
from tools.base import ToolSlot


class RecordingBrowserTool:
    def __init__(
        self,
        *,
        browser: DirectHttpBrowserTool,
        agent_runs: AgentRunRepository,
        run_id: str,
        campaign_id: str,
        step_id: str | None,
    ) -> None:
        self.browser = browser
        self.agent_runs = agent_runs
        self.run_id = run_id
        self.campaign_id = campaign_id
        self.step_id = step_id

    def inspect(self, url: str):
        tool_call = self.agent_runs.start_tool_call(
            run_id=self.run_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            tool_name="browser:inspect",
            reason="inspect lead website for public evidence",
            args={"url": url},
        )
        try:
            result = self.browser.inspect(url)
        except Exception as exc:
            self.agent_runs.fail_tool_call(tool_call.id, str(exc))
            raise
        self.agent_runs.complete_tool_call(tool_call.id, CampaignService._json_safe(result))
        return result


class RecordingLLMClient:
    def __init__(
        self,
        *,
        llm: LLMClient,
        agent_runs: AgentRunRepository,
        run_id: str,
        campaign_id: str,
        step_id: str | None,
    ) -> None:
        self.llm = llm
        self.agent_runs = agent_runs
        self.run_id = run_id
        self.campaign_id = campaign_id
        self.step_id = step_id

    def generate_object(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        response_model: type[BaseModel],
        context: dict[str, Any] | None = None,
    ) -> BaseModel:
        llm_call = self.agent_runs.start_llm_call(
            run_id=self.run_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            task=task,
            reason=system,
            args={
                "task": task,
                "response_model": response_model.__name__,
                "system": system,
                "prompt": truncate(prompt, 30000),
                "context": CampaignService._json_safe(context or {}),
            },
        )
        try:
            result = self.llm.generate_object(
                task=task,
                system=system,
                prompt=prompt,
                response_model=response_model,
                context=context,
            )
        except Exception as exc:
            self.agent_runs.fail_tool_call(llm_call.id, str(exc))
            raise
        self.agent_runs.complete_tool_call(llm_call.id, CampaignService._json_safe(result))
        return result


class CampaignService:
    def __init__(
        self,
        *,
        session: Session,
        llm: LLMClient,
        search_tool: SearchTool,
        browser: DirectHttpBrowserTool,
        email: EmailTool | None = None,
        google_places_api_key: str | None = None,
        google_places_api_endpoint: str | None = None,
        apify_api_token: str | None = None,
        apify_api_base_url: str | None = None,
        apify_source_provider_id: str = "apify_actor",
        apify_actor_id: str | None = None,
        apify_actor_input_template: str | None = None,
        apify_actor_result_mapping: str | None = None,
        apify_actor_max_charge_usd: float | None = None,
        apify_sources: list[dict[str, Any]] | None = None,
        contact_verification_provider: str = "syntax",
        email_verification_endpoint: str | None = None,
        email_verification_api_key: str | None = None,
        bouncer_api_key: str | None = None,
        bouncer_api_endpoint: str | None = None,
        zerobounce_api_key: str | None = None,
        zerobounce_api_endpoint: str | None = None,
        embedding: EmbeddingClient | None = None,
        semantic_cache_min_score: float = 0.78,
        semantic_cache_min_results: int = 5,
        timeout_seconds: float = 20.0,
        workspace_id: str | None = None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.search_tool = search_tool
        self.browser = browser
        self.email = email or EmailTool()
        self.embedding = embedding or MissingEmbeddingClient()
        self.semantic_cache_min_score = semantic_cache_min_score
        self.semantic_cache_min_results = semantic_cache_min_results
        self.google_places_api_key = google_places_api_key
        self.google_places_api_endpoint = google_places_api_endpoint
        self.apify_api_token = apify_api_token
        self.apify_api_base_url = apify_api_base_url
        self.apify_source_provider_id = apify_source_provider_id
        self.apify_actor_id = apify_actor_id
        self.apify_actor_input_template = apify_actor_input_template
        self.apify_actor_result_mapping = apify_actor_result_mapping
        self.apify_actor_max_charge_usd = apify_actor_max_charge_usd
        self.apify_sources = apify_sources
        self.contact_verification_provider = contact_verification_provider
        self.email_verification_endpoint = email_verification_endpoint
        self.email_verification_api_key = email_verification_api_key
        self.bouncer_api_key = bouncer_api_key
        self.bouncer_api_endpoint = bouncer_api_endpoint
        self.zerobounce_api_key = zerobounce_api_key
        self.zerobounce_api_endpoint = zerobounce_api_endpoint
        self.timeout_seconds = timeout_seconds
        self.products = ProductRepository(session, workspace_id=workspace_id)
        self.campaigns = CampaignRepository(session, workspace_id=workspace_id)
        self.campaign_sources = CampaignSourceRepository(session)
        self.agent_runs = AgentRunRepository(session)
        self.icp_presets = ICPPresetService()
        self.source_presets = SourcePresetService()
        self.discovery_candidates = DiscoveryCandidateRepository(session)
        self.leads = LeadRepository(session, embedding=self.embedding, workspace_id=workspace_id)
        self.messages = MessageRepository(session, workspace_id=workspace_id)
        self.conversations = ConversationRepository(session, workspace_id=workspace_id)
        self.memory = MemoryRepository(session)

    def create(self, campaign: CampaignCreate) -> CampaignModel:
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        campaign = self._apply_source_preset_policy(campaign)
        campaign_model = self.campaigns.create(campaign)
        sources = self.source_presets.expand_for_campaign(
            campaign_id=campaign_model.id,
            campaign=campaign,
            product=product,
        )
        if sources:
            self.campaign_sources.create_many(sources)
        return campaign_model

    @staticmethod
    def _apply_source_preset_policy(campaign: CampaignCreate) -> CampaignCreate:
        if campaign.source_preset_id or not campaign.source_input:
            return campaign
        validate_google_places_query(campaign.source_input)
        source_inputs = {
            **campaign.source_inputs,
            "source_selection": "google_places_local_business",
            "source_selection_reason": (
                "Explicit discovery query without a source preset defaults to the "
                "precise local-business source, not broad web search."
            ),
        }
        return campaign.model_copy(
            update={
                "source_preset_id": "google-places-local-business",
                "source_inputs": source_inputs,
            }
        )

    def list(self) -> list[CampaignModel]:
        return self.campaigns.list()

    def get(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.get(campaign_id)

    def update(self, campaign_id: str, update: CampaignUpdate) -> CampaignModel:
        return self.campaigns.update(campaign_id, update)

    def delete(self, campaign_id: str) -> None:
        self.campaigns.delete(campaign_id)

    def preflight(self, campaign_id: str) -> CampaignPreflightRead:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        checks = self._preflight_checks(campaign, product)
        return CampaignPreflightRead(
            campaign_id=campaign_id,
            ready=all(check.status != "failed" for check in checks if check.required),
            checks=checks,
        )

    def pause(self, campaign_id: str) -> CampaignModel:
        return self.campaigns.update_status(campaign_id, CampaignStatus.PAUSED)

    def resume(self, campaign_id: str) -> CampaignModel:
        campaign = self.campaigns.get(campaign_id)
        stage_to_status = {
            CampaignStage.DISCOVERY.value: CampaignStatus.DISCOVERING,
            CampaignStage.RESEARCH.value: CampaignStatus.RESEARCHING,
            CampaignStage.QUALIFICATION.value: CampaignStatus.QUALIFYING,
            CampaignStage.OUTREACH.value: CampaignStatus.AWAITING_APPROVAL,
            CampaignStage.RESPONSE.value: CampaignStatus.TRACKING,
            CampaignStage.COMPLETE.value: CampaignStatus.COMPLETED,
        }
        return self.campaigns.update_status(
            campaign_id, stage_to_status.get(campaign.stage, CampaignStatus.TRACKING)
        )

    def run_campaign(
        self,
        campaign_id: str,
        *,
        agent_run_id: str | None = None,
        draft_outreach: bool = True,
    ) -> CampaignRunSummary:
        campaign = self.campaigns.get(campaign_id)
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        campaign_read = CampaignRead.model_validate(campaign)
        preset = self.icp_presets.get(campaign_read.icp_preset_id)

        try:
            self._assert_runnable_campaign(campaign_read)
            self._assert_preflight_ready(campaign_read, product)
            if agent_run_id:
                self.agent_runs.start(agent_run_id)

            discovered = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.DISCOVERY.value,
                sequence=1,
                objective="Discover potential customers that match the product ICP.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda step_id: DiscoveryWorkflow(
                    campaigns=self.campaigns,
                    campaign_sources=self.campaign_sources,
                    candidates=self.discovery_candidates,
                    leads=self.leads,
                    memory=self.memory,
                    search_tool=self.search_tool,
                    google_places_api_key=self.google_places_api_key,
                    google_places_api_endpoint=self.google_places_api_endpoint,
                    apify_api_token=self.apify_api_token,
                    apify_api_base_url=self.apify_api_base_url,
                    apify_source_provider_id=self.apify_source_provider_id,
                    apify_actor_id=self.apify_actor_id,
                    apify_actor_input_template=self.apify_actor_input_template,
                    apify_actor_result_mapping=self.apify_actor_result_mapping,
                    apify_actor_max_charge_usd=self.apify_actor_max_charge_usd,
                    apify_sources=self.apify_sources,
                    embedding=self.embedding,
                    semantic_cache_min_score=self.semantic_cache_min_score,
                    semantic_cache_min_results=self.semantic_cache_min_results,
                    timeout_seconds=self.timeout_seconds,
                    **self._tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            researched = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.RESEARCH.value,
                sequence=2,
                objective="Research discovered leads with available public information.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: ResearchWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    browser=self._browser_for_step(agent_run_id, campaign_id, _step_id),
                    llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            contacted = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.CONTACT.value,
                sequence=3,
                objective="Find the first good reachable contact point for each researched lead.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: ContactWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.CONTACT),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            verified = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.VERIFY.value,
                sequence=4,
                objective="Verify contact points before qualification and outreach drafting.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: VerifyWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.VERIFY),
                    verification_tool=self._verification_tool(),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            signaled = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=ToolSlot.SIGNAL.value,
                sequence=5,
                objective="Accumulate public signals used by qualification and campaign insights.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: SignalWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    slot_config=preset.slot_config(ToolSlot.SIGNAL),
                    **self._slot_tool_call_callbacks(
                        agent_run_id=agent_run_id,
                        campaign_id=campaign_id,
                        step_id=_step_id,
                    ),
                ).run(product, campaign_read),
            )

            campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
            qualified = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.QUALIFICATION.value,
                sequence=6,
                objective="Score researched leads against the product qualification criteria.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: QualificationWorkflow(
                    campaigns=self.campaigns,
                    leads=self.leads,
                    memory=self.memory,
                    llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                ).run(product, campaign_read),
            )

            if draft_outreach:
                campaign_read = CampaignRead.model_validate(self.campaigns.get(campaign_id))
                drafts = self._run_agent_step(
                    agent_run_id=agent_run_id,
                    campaign_id=campaign_id,
                    phase=CampaignStage.OUTREACH.value,
                    sequence=7,
                    objective="Draft personalized outreach and queue messages for human approval.",
                    input_snapshot=self._campaign_step_input(product, campaign_read),
                    action=lambda _step_id: OutreachWorkflow(
                        campaigns=self.campaigns,
                        leads=self.leads,
                        messages=self.messages,
                        memory=self.memory,
                        llm=self._llm_for_step(agent_run_id, campaign_id, _step_id),
                    ).run(product, campaign_read),
                )
            else:
                drafts = []
                self.campaigns.update_status(
                    campaign_id,
                    CampaignStatus.COMPLETED,
                    stage=CampaignStage.COMPLETE,
                )

            if agent_run_id:
                self._log_hit_rates(agent_run_id=agent_run_id, campaign_id=campaign_id, product_id=product.id)

            summary = CampaignRunSummary(
                campaign=CampaignRead.model_validate(self.campaigns.get(campaign_id)),
                discovered_lead_count=len(discovered),
                researched_lead_count=len(researched),
                contacted_lead_count=len(contacted),
                verified_lead_count=len(verified),
                signaled_lead_count=len(signaled),
                qualified_lead_count=sum(
                    1
                    for lead in qualified
                    if lead.qualification and lead.qualification.qualified
                ),
                drafted_message_count=len(drafts),
            )
            if agent_run_id:
                self.agent_runs.complete(agent_run_id, summary.model_dump(mode="json"))
            return summary
        except Exception as exc:
            if agent_run_id:
                self.agent_runs.fail(agent_run_id, str(exc))
            raise

    def run_contact_listing(
        self,
        campaign_id: str,
        *,
        agent_run_id: str | None = None,
    ) -> CampaignRunSummary:
        cached_summary = self._run_cached_contact_listing(campaign_id, agent_run_id=agent_run_id)
        if cached_summary is not None:
            return cached_summary
        return self.run_campaign(
            campaign_id,
            agent_run_id=agent_run_id,
            draft_outreach=False,
        )

    def _run_cached_contact_listing(
        self,
        campaign_id: str,
        *,
        agent_run_id: str | None,
    ) -> CampaignRunSummary | None:
        campaign = self.campaigns.get(campaign_id)
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        campaign_read = CampaignRead.model_validate(campaign)
        self._assert_runnable_campaign(campaign_read)

        cached_rows = self._cached_discovery_rows(product=product, campaign=campaign_read)
        if not cached_rows:
            return None

        assessed_rows = self._assessed_cached_rows(product=product, rows=cached_rows)
        if not any(assessment.is_promotable for _, _, assessment in assessed_rows):
            return None

        try:
            if agent_run_id:
                self.agent_runs.start(agent_run_id)

            self.campaigns.update_status(
                campaign_id,
                CampaignStatus.DISCOVERING,
                stage=CampaignStage.DISCOVERY,
            )
            discovered = self._run_agent_step(
                agent_run_id=agent_run_id,
                campaign_id=campaign_id,
                phase=CampaignStage.DISCOVERY.value,
                sequence=1,
                objective="List contacts from the cached canonical business pool.",
                input_snapshot=self._campaign_step_input(product, campaign_read),
                action=lambda _step_id: self._create_cached_contact_listing(
                    product=product,
                    campaign=campaign_read,
                    assessed_rows=assessed_rows,
                ),
            )

            self.campaigns.update_status(
                campaign_id,
                CampaignStatus.RESEARCHING,
                stage=CampaignStage.RESEARCH,
            )
            self.campaigns.update_status(
                campaign_id,
                CampaignStatus.QUALIFYING,
                stage=CampaignStage.QUALIFICATION,
            )
            completed_campaign = self.campaigns.update_status(campaign_id, CampaignStatus.COMPLETED)
            summary = CampaignRunSummary(
                campaign=CampaignRead.model_validate(completed_campaign),
                discovered_lead_count=len(discovered),
                researched_lead_count=len(discovered),
                contacted_lead_count=sum(1 for lead in discovered if lead.contact_email),
                verified_lead_count=sum(
                    1
                    for lead in discovered
                    if lead.verification_status != ContactVerificationStatus.UNVERIFIED
                ),
                signaled_lead_count=len(discovered),
                qualified_lead_count=sum(
                    1
                    for lead in discovered
                    if lead.qualification and lead.qualification.qualified
                ),
                drafted_message_count=0,
            )
            if agent_run_id:
                self.agent_runs.complete(agent_run_id, summary.model_dump(mode="json"))
            return summary
        except Exception as exc:
            if agent_run_id:
                self.agent_runs.fail(agent_run_id, str(exc))
            raise

    def _cached_discovery_rows(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
    ) -> list[dict[str, Any]]:
        sources = [
            CampaignSourceRead.model_validate(source)
            for source in self.campaign_sources.list_by_campaign(
                campaign.id,
                slot=CampaignSourceSlot.DISCOVERY,
                enabled_only=True,
            )
        ]
        canonical = CanonicalRepository(self.session, embedding=self.embedding)
        min_results = min(self.semantic_cache_min_results, campaign.max_leads)
        for source in sources:
            source_query = str(source.input.get("query") or campaign.source_input or "").strip()
            semantic_rows = canonical.list_semantic_discovery_results(
                source_inputs=source.input,
                source_input=source_query,
                limit=campaign.max_leads,
                min_score=self.semantic_cache_min_score,
                min_results=min_results,
            )
            if semantic_rows:
                return _rows_with_semantic_context(semantic_rows)

        cached_results: list[dict[str, Any]] = []
        for source in sources:
            limit = int(source.config.get("limit") or campaign.max_leads)
            cached_rows = canonical.list_cached_discovery_results(
                source=source.provider_id,
                source_input=source.input,
                limit=limit,
            )
            if cached_rows:
                cached_results.extend(
                    _rows_with_source_context(
                        rows=cached_rows,
                        source=source,
                        from_cache=True,
                    )
                )
        if len(cached_results) < min_results:
            return []
        return cached_results[: campaign.max_leads]

    @staticmethod
    def _assessed_cached_rows(
        *,
        product: ProductRead,
        rows: list[dict[str, Any]],
    ):
        assessed = []
        for row in rows:
            search_result = SearchResult.model_validate(row)
            assessed.append((row, search_result, assess_discovery_candidate(search_result, product)))
        return assessed

    def _create_cached_contact_listing(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        assessed_rows,
    ) -> list[LeadRead]:
        discovered: list[LeadRead] = []
        for row, search_result, assessment in assessed_rows:
            candidate = self.discovery_candidates.create(
                DiscoveryCandidateCreate(
                    campaign_id=campaign.id,
                    product_id=product.id,
                    query=str(row.get("discovery_query") or search_result.raw.get("query") or ""),
                    title=search_result.title,
                    url=search_result.url,
                    snippet=search_result.snippet,
                    geography=search_result.geography,
                    contact_email=search_result.contact_email,
                    source=search_result.source,
                    raw=row,
                    candidate_type=assessment.candidate_type,
                    confidence=assessment.confidence,
                    rejection_reason=assessment.rejection_reason,
                )
            )
            if not assessment.is_promotable or len(discovered) >= campaign.max_leads:
                continue
            lead = self.leads.create_from_cached_result(
                campaign_id=campaign.id,
                product_id=product.id,
                result=row,
            )
            self.discovery_candidates.mark_promoted(candidate.id, lead.id)
            lead = self.leads.attach_research(
                lead.id,
                _cached_lead_research(
                    product=product,
                    lead=LeadRead.model_validate(lead),
                    row=row,
                    confidence=assessment.confidence,
                ),
            )
            lead = self.leads.attach_qualification(
                lead.id,
                _cached_qualification(
                    product=product,
                    lead=LeadRead.model_validate(lead),
                    row=row,
                    confidence=assessment.confidence,
                ),
            )
            discovered.append(LeadRead.model_validate(lead))

        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Cached contact listing produced {len(discovered)} leads.",
                tags=["discovery", "cache", product.target_customer],
            )
        )
        return discovered

    def _log_hit_rates(self, *, agent_run_id: str, campaign_id: str, product_id: str) -> None:
        """Surface per-provider hit-rate for this run as a readable observation.

        This is manual feedback for the operator (see ICP integration model) --
        it is logged, never used to auto-tune preset selection.
        """
        rows = [
            tool_call.observation
            for tool_call in self.agent_runs.list_tool_calls(agent_run_id)
            if isinstance(tool_call.observation, dict)
            and "confidence" in tool_call.observation
            and "slot" in tool_call.observation
        ]
        if not rows:
            return
        hit_rates = calculate_hit_rates(rows)
        summary_line = "; ".join(
            f"{rate.slot}/{rate.provider}: {rate.accepted}/{rate.calls} accepted"
            for rate in hit_rates
        )
        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product_id,
                campaign_id=campaign_id,
                type=ObservationType.TOOL_HIT_RATE,
                content=f"Tool hit-rate for this run: {summary_line}",
                tags=["hit_rate"],
            )
        )

    def _verification_tool(self) -> EmailVerificationTool:
        return EmailVerificationTool(
            provider=self.contact_verification_provider,
            endpoint=self.email_verification_endpoint,
            api_key=self.email_verification_api_key,
            bouncer_api_key=self.bouncer_api_key,
            bouncer_api_endpoint=self.bouncer_api_endpoint,
            zerobounce_api_key=self.zerobounce_api_key,
            zerobounce_api_endpoint=self.zerobounce_api_endpoint,
            timeout_seconds=self.timeout_seconds,
        )

    def metrics(self, campaign_id: str) -> CampaignMetrics:
        leads = [
            LeadRead.model_validate(model)
            for model in self.leads.list_by_campaign(campaign_id)
        ]
        messages = [
            MessageRead.model_validate(model)
            for model in self.messages.list_by_campaign(campaign_id)
        ]
        conversations = [
            ConversationRead.model_validate(model)
            for model in self.conversations.list_by_campaign(campaign_id)
        ]
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        return calculate_campaign_metrics(
            leads=leads,
            messages=messages,
            conversations=conversations,
            goal_type=campaign.goal_type,
        )

    def _assert_preflight_ready(self, campaign: CampaignRead, product: ProductRead) -> None:
        preflight = CampaignPreflightRead(
            campaign_id=campaign.id,
            ready=True,
            checks=self._preflight_checks(campaign, product),
        )
        failures = [check for check in preflight.checks if check.required and check.status == "failed"]
        if failures:
            raise ConflictError(
                "discovery run cannot start until required integrations are configured",
                {"failures": [failure.model_dump(mode="json") for failure in failures]},
            )

    def _preflight_checks(
        self, campaign: CampaignRead, product: ProductRead
    ) -> list[CampaignPreflightCheck]:
        del product
        sources = [
            CampaignSourceRead.model_validate(source)
            for source in self.campaign_sources.list_by_campaign(
                campaign.id,
                slot=CampaignSourceSlot.DISCOVERY,
                enabled_only=True,
            )
        ]
        checks = [
            CampaignPreflightCheck(
                name="Run status",
                status="ok" if campaign.status in {CampaignStatus.DRAFT, CampaignStatus.PAUSED} else "failed",
                detail=f"Run is {campaign.status.value}.",
            )
        ]

        if sources:
            registry = SourceAdapterRegistry(
                search_tool=self.search_tool,
                google_places_api_key=self.google_places_api_key,
                google_places_api_endpoint=self.google_places_api_endpoint,
                apify_api_token=self.apify_api_token,
                apify_api_base_url=self.apify_api_base_url,
                apify_source_provider_id=self.apify_source_provider_id,
                apify_actor_id=self.apify_actor_id,
                apify_actor_input_template=self.apify_actor_input_template,
                apify_actor_result_mapping=self.apify_actor_result_mapping,
                apify_actor_max_charge_usd=self.apify_actor_max_charge_usd,
                apify_sources=self.apify_sources,
                timeout_seconds=self.timeout_seconds,
            )
            provider_ids = list(dict.fromkeys(source.provider_id for source in sources))
            unregistered = [provider_id for provider_id in provider_ids if provider_id not in registry.adapters]
            missing_config = registry.missing_configuration(provider_ids)
            if "configured_search" in provider_ids and not self.search_tool.is_configured:
                missing_config.append("configured_search")
            missing_config = list(dict.fromkeys(missing_config))
            required_missing_config = [
                provider_id
                for provider_id in missing_config
                if provider_id != "configured_search" or self.search_tool.require_config
            ]
            failures = [*unregistered, *missing_config]
            required_failures = [*unregistered, *required_missing_config]
            checks.append(
                CampaignPreflightCheck(
                    name="Discovery sources",
                    status="ok" if not failures else "failed" if required_failures else "warning",
                    detail=(
                        f"{len(sources)} discovery source(s): {', '.join(provider_ids)}"
                        if not failures
                        else f"Missing or unavailable source provider(s): {', '.join(failures)}"
                    ),
                    required=bool(required_failures),
                )
            )
        else:
            checks.append(
                CampaignPreflightCheck(
                    name="Discovery sources",
                    status="failed",
                    detail="No discovery sources configured.",
                    required=True,
                )
            )

        if isinstance(self.llm, MissingLLMClient):
            llm_status = "failed"
            llm_detail = "Configure OPENAI_API_KEY or LLM_JSON_ENDPOINT."
        else:
            llm_status = "ok"
            llm_detail = self.llm.__class__.__name__
        checks.append(CampaignPreflightCheck(name="LLM provider", status=llm_status, detail=llm_detail))

        checks.append(
            CampaignPreflightCheck(
                name="Email provider",
                status="ok" if self.messages_can_send_real_email() else "failed",
                detail=(
                    f"{self.email.provider} email provider ready"
                    if self.messages_can_send_real_email()
                    else email_provider_setup_hint(self.email.provider)
                ),
                required=False,
            )
        )

        verification_status, verification_detail, verification_required = self._contact_verification_check()
        checks.append(
            CampaignPreflightCheck(
                name="Contact verification",
                status=verification_status,
                detail=verification_detail,
                required=verification_required,
            )
        )

        checks.append(
            CampaignPreflightCheck(
                name="Website inspection",
                status="ok",
                detail="Direct HTTP website inspection is enabled.",
                required=False,
            )
        )
        return checks

    def messages_can_send_real_email(self) -> bool:
        return self.email.is_configured

    def _contact_verification_check(self) -> tuple[str, str, bool]:
        provider = (self.contact_verification_provider or "syntax").strip().lower()
        if provider in {"syntax", "local"}:
            return (
                "warning",
                "Local syntax-only verification is enabled; deliverability is not externally checked.",
                False,
            )
        if provider == "http":
            if self.email_verification_endpoint:
                return "ok", "Generic HTTP contact verification is configured.", True
            return "failed", "Configure EMAIL_VERIFICATION_ENDPOINT for generic HTTP verification.", True
        if provider == "bouncer":
            if self.bouncer_api_key or self.email_verification_api_key:
                return "ok", "Bouncer contact verification is configured.", True
            return "failed", "Configure BOUNCER_API_KEY for Bouncer contact verification.", True
        if provider == "zerobounce":
            if self.zerobounce_api_key or self.email_verification_api_key:
                return "ok", "ZeroBounce contact verification is configured.", True
            return "failed", "Configure ZEROBOUNCE_API_KEY for ZeroBounce contact verification.", True
        return "failed", f"Unknown contact verification provider: {provider}.", True

    @staticmethod
    def _assert_runnable_campaign(campaign: CampaignRead) -> None:
        if campaign.status not in {CampaignStatus.DRAFT, CampaignStatus.PAUSED}:
            raise ConflictError(
                "campaign can only be run from draft or paused status",
                {"campaign_id": campaign.id, "status": campaign.status.value},
            )

    def _run_agent_step(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        phase: str,
        sequence: int,
        objective: str,
        input_snapshot: dict[str, Any],
        action: Callable[[str | None], Any],
    ) -> Any:
        if not agent_run_id:
            return action(None)

        step = self.agent_runs.start_step(
            run_id=agent_run_id,
            campaign_id=campaign_id,
            phase=phase,
            sequence=sequence,
            objective=objective,
            input_snapshot=input_snapshot,
        )
        try:
            result = action(step.id)
        except Exception as exc:
            self.agent_runs.fail_step(step.id, str(exc))
            raise

        output_snapshot = self._result_snapshot(result)
        self.agent_runs.complete_step(
            step.id,
            output_snapshot=output_snapshot,
            observation={
                "phase": phase,
                "completed": True,
                **output_snapshot,
            },
        )
        return result

    @staticmethod
    def _campaign_step_input(product: ProductRead, campaign: CampaignRead) -> dict[str, Any]:
        return {
            "product_id": product.id,
            "product_name": product.product_name,
            "campaign_id": campaign.id,
            "campaign_status": campaign.status.value,
            "campaign_stage": campaign.stage.value,
            "goal_type": campaign.goal_type.value,
            "icp_preset_id": campaign.icp_preset_id,
            "source_preset_id": campaign.source_preset_id,
            "max_leads": campaign.max_leads,
        }

    @staticmethod
    def _result_snapshot(result: Any) -> dict[str, Any]:
        if isinstance(result, list):
            ids = [getattr(row, "id", None) for row in result]
            return {
                "count": len(result),
                "ids": [row_id for row_id in ids if row_id is not None][:50],
            }
        return {"result": CampaignService._json_safe(result)}

    def _tool_call_callbacks(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> dict[str, Callable[..., Any] | None]:
        if agent_run_id is None:
            return {
                "on_tool_start": None,
                "on_tool_success": None,
                "on_tool_error": None,
            }

        def on_tool_start(action: ToolAction, iteration: int) -> str:
            tool_call = self.agent_runs.start_tool_call(
                run_id=agent_run_id,
                campaign_id=campaign_id,
                step_id=step_id,
                tool_name=action.tool_name,
                reason=action.reason,
                args={"iteration": iteration, **self._json_safe(action.args)},
            )
            return tool_call.id

        def on_tool_success(tool_call_id: str, observation: Any) -> None:
            self.agent_runs.complete_tool_call(tool_call_id, self._json_safe(observation))

        def on_tool_error(tool_call_id: str, error: Exception) -> None:
            self.agent_runs.fail_tool_call(tool_call_id, str(error))

        return {
            "on_tool_start": on_tool_start,
            "on_tool_success": on_tool_success,
            "on_tool_error": on_tool_error,
        }

    def _slot_tool_call_callbacks(
        self,
        *,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> dict[str, Callable[..., Any] | None]:
        if agent_run_id is None:
            return {
                "on_tool_start": None,
                "on_tool_success": None,
                "on_tool_error": None,
            }

        def on_tool_start(tool_name: str, args: dict[str, Any], reason: str) -> str:
            tool_call = self.agent_runs.start_tool_call(
                run_id=agent_run_id,
                campaign_id=campaign_id,
                step_id=step_id,
                tool_name=tool_name,
                reason=reason,
                args=self._json_safe(args),
            )
            return tool_call.id

        def on_tool_success(tool_call_id: str, observation: Any) -> None:
            self.agent_runs.complete_tool_call(tool_call_id, self._json_safe(observation))

        def on_tool_error(tool_call_id: str, error: Exception) -> None:
            self.agent_runs.fail_tool_call(tool_call_id, str(error))

        return {
            "on_tool_start": on_tool_start,
            "on_tool_success": on_tool_success,
            "on_tool_error": on_tool_error,
        }

    def _llm_for_step(
        self,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> LLMClient:
        if agent_run_id is None:
            return self.llm
        return RecordingLLMClient(
            llm=self.llm,
            agent_runs=self.agent_runs,
            run_id=agent_run_id,
            campaign_id=campaign_id,
            step_id=step_id,
        )

    def _browser_for_step(
        self,
        agent_run_id: str | None,
        campaign_id: str,
        step_id: str | None,
    ) -> DirectHttpBrowserTool:
        if agent_run_id is None:
            return self.browser
        return RecordingBrowserTool(
            browser=self.browser,
            agent_runs=self.agent_runs,
            run_id=agent_run_id,
            campaign_id=campaign_id,
            step_id=step_id,
        )

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [CampaignService._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [CampaignService._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): CampaignService._json_safe(item) for key, item in value.items()}
        if value is None or isinstance(value, str | int | float | bool):
            return value
        return str(value)


def _cached_lead_research(
    *,
    product: ProductRead,
    lead: LeadRead,
    row: dict[str, Any],
    confidence: int,
) -> LeadResearch:
    signals = _cached_signals(row=row, lead=lead)
    summary = truncate(
        lead.description
        or f"{lead.company_name} matched cached business-pool evidence for {product.product_name}.",
        700,
    )
    return LeadResearch(
        summary=summary,
        lead_type=LeadFitType.TARGET_CUSTOMER,
        business_type=_cached_business_type(product=product, row=row, lead=lead),
        geography=lead.geography,
        website_url=lead.website_url,
        contact_email=lead.contact_email,
        contact_candidates=[lead.contact_email] if lead.contact_email else [],
        signals=signals,
        pain_indicators=[],
        disqualifiers=[],
        sources=_cached_sources(row=row, lead=lead),
        confidence=max(0, min(100, confidence)),
    )


def _cached_qualification(
    *,
    product: ProductRead,
    lead: LeadRead,
    row: dict[str, Any],
    confidence: int,
) -> QualificationResult:
    signals = _cached_signals(row=row, lead=lead)
    missing = _cached_missing_evidence(row=row, lead=lead)
    score = _cached_fit_score(row=row, lead=lead, confidence=confidence)
    qualified = score >= 65
    fit_status = (
        AgentFitStatus.GOOD_FIT
        if score >= 80
        else AgentFitStatus.MAYBE
        if qualified
        else AgentFitStatus.NOT_FIT
    )
    return QualificationResult(
        qualified=qualified,
        fit_status=fit_status,
        score=score,
        rationale=(
            f"{lead.company_name} matched cached public business evidence for "
            f"{product.product_name}."
        ),
        positive_signals=signals[:6],
        missing_evidence=missing,
        risks=[],
        criteria=[
            CriterionScore(
                criterion_id=criterion.id or criterion.label,
                label=criterion.label,
                score=score,
                evidence=signals[:3],
                missing_evidence=missing[:2],
            )
            for criterion in product.qualification_criteria
        ],
        recommended_next_step=(
            "Review the contact and shortlist manually before outreach."
            if qualified
            else "Review manually before taking action."
        ),
    )


def _cached_fit_score(*, row: dict[str, Any], lead: LeadRead, confidence: int) -> int:
    score = max(65, min(90, confidence))
    if lead.contact_email:
        score += 5
    if _cached_phone(row):
        score += 3
    if _cached_has_quote_signal(row):
        score += 4
    if lead.verification_status == ContactVerificationStatus.VALID:
        score += 3
    return max(0, min(95, score))


def _cached_missing_evidence(*, row: dict[str, Any], lead: LeadRead) -> list[str]:
    missing: list[str] = []
    if not lead.contact_email:
        missing.append("Direct email not found.")
    elif lead.verification_status == ContactVerificationStatus.UNVERIFIED:
        missing.append("Email deliverability not verified.")
    if not _cached_has_quote_signal(row):
        missing.append("Explicit quote or estimate signal not found.")
    return missing


def _cached_signals(*, row: dict[str, Any], lead: LeadRead) -> list[str]:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    enrichment = raw.get("website_enrichment") if isinstance(raw.get("website_enrichment"), dict) else {}
    signals: list[str] = []
    signals.extend(signal for signal in raw.get("signals", []) if isinstance(signal, str))
    signals.extend(signal for signal in enrichment.get("service_signals", []) if isinstance(signal, str))
    signals.extend(signal for signal in enrichment.get("quote_signals", []) if isinstance(signal, str))
    if enrichment.get("has_quote_form"):
        signals.append("quote or estimate form")
    if enrichment.get("has_contact_form"):
        signals.append("contact form")
    if lead.contact_email:
        signals.append("public email")
    if _cached_phone(row):
        signals.append("public phone")
    if not signals and lead.description:
        signals.append(truncate(lead.description, 120))
    return list(dict.fromkeys(signals))[:8]


def _cached_has_quote_signal(row: dict[str, Any]) -> bool:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    enrichment = raw.get("website_enrichment") if isinstance(raw.get("website_enrichment"), dict) else {}
    return bool(enrichment.get("has_quote_form") or enrichment.get("quote_signals"))


def _cached_phone(row: dict[str, Any]) -> str | None:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    for source in (row, raw):
        for key in ("phone", "contact_phone", "nationalPhoneNumber", "internationalPhoneNumber"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _cached_sources(*, row: dict[str, Any], lead: LeadRead) -> list[str]:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    enrichment = raw.get("website_enrichment") if isinstance(raw.get("website_enrichment"), dict) else {}
    sources = []
    if lead.website_url:
        sources.append(lead.website_url)
    if isinstance(enrichment.get("inspected_urls"), list):
        sources.extend(url for url in enrichment["inspected_urls"] if isinstance(url, str))
    return list(dict.fromkeys(sources))[:5]


def _cached_business_type(*, product: ProductRead, row: dict[str, Any], lead: LeadRead) -> str:
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    enrichment = raw.get("website_enrichment") if isinstance(raw.get("website_enrichment"), dict) else {}
    service_signals = enrichment.get("service_signals")
    if isinstance(service_signals, list) and service_signals:
        return ", ".join(str(signal) for signal in service_signals[:3])
    return lead.description or product.target_customer


def email_provider_setup_hint(provider: str) -> str:
    if provider == "gmail":
        return (
            "Configure EMAIL_PROVIDER=gmail with Google OAuth credentials, "
            "GOOGLE_TOKEN_ENCRYPTION_KEY, and a connected Gmail account."
        )
    if provider == "resend":
        return "Configure EMAIL_PROVIDER=resend with RESEND_API_KEY and EMAIL_FROM_ADDRESS."
    if provider == "http":
        return "Configure EMAIL_PROVIDER=http with EMAIL_PROVIDER_ENDPOINT."
    return "Configure EMAIL_PROVIDER with a real sender before outreach."
