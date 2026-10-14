from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from agents.embeddings import EmbeddingClient, MissingEmbeddingClient
from agents.llm import LLMClient
from campaign_sources.repository import CampaignSourceRepository
from campaigns.repository import CampaignRepository
from campaigns.schemas import (
    CampaignCreate,
    CampaignRead,
    CampaignStage,
    CampaignStatus,
    CampaignUpdate,
)
from conversations.repository import ConversationRepository
from conversations.schemas import ConversationRead
from db.models import CampaignModel
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateCreate, DiscoveryCandidateType
from evaluation.campaign_metrics import calculate_campaign_metrics
from evaluation.lead_scoring import build_cached_lead_research, score_cached_lead
from evaluation.schemas import CampaignMetrics
from icp.service import ICPPresetService
from leads.repository import LeadRepository
from leads.selection import select_campaign_results
from leads.schemas import (
    AgentFitStatus,
    LeadRead,
    QualificationResult,
)
from memory.repository import MemoryRepository
from memory.schemas import CampaignMemoryCreate, ObservationType
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from products.discovery_policy import validate_google_places_query
from products.repository import ProductRepository
from products.schemas import ProductRead
from source_presets.service import SourcePresetService
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.search import SearchResult, SearchTool
from territories.opportunity_audit import BusinessOpportunityAuditor


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
        opportunity_auditor: BusinessOpportunityAuditor | None = None,
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
        self.opportunity_auditor = opportunity_auditor
        self.products = ProductRepository(session, workspace_id=workspace_id)
        self.campaigns = CampaignRepository(session, workspace_id=workspace_id)
        self.campaign_sources = CampaignSourceRepository(session)
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

    def create_profile_delivery(self, campaign: CampaignCreate) -> CampaignModel:
        """Create a delivery container without configuring discovery sources."""
        return self.campaigns.create(campaign)

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

    def results(self, campaign_id: str) -> list[LeadRead]:
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        leads = [
            LeadRead.model_validate(lead)
            for lead in self.leads.list_by_campaign(campaign_id)
        ]
        return select_campaign_results(campaign, leads)

    def materialize_existing_matches(
        self,
        campaign_id: str,
        rows: list[dict[str, Any]],
    ) -> list[LeadRead]:
        """Append eligible database matches without invoking external tools."""
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        product = ProductRead.model_validate(self.products.get(campaign.product_id))
        indexed_rows = self._indexed_cached_rows(rows=rows)
        return self._create_existing_match_listing(
            product=product,
            campaign=campaign,
            indexed_rows=indexed_rows,
        )

    def materialize_profile_matches(
        self,
        campaign_id: str,
        rows: list[dict[str, Any]],
    ) -> list[LeadRead]:
        """Materialize deterministic audience matches without product or model judgment."""
        campaign = CampaignRead.model_validate(self.campaigns.get(campaign_id))
        created: list[LeadRead] = []
        for row in rows[: campaign.max_leads]:
            profile_match = (row.get("raw") or {}).get("profile_match") or {}
            signal_evidence = profile_match.get("signals") or {}
            if not isinstance(signal_evidence, dict):
                signal_evidence = {}
            matched_signals = [
                key
                for key, evidence in signal_evidence.items()
                if isinstance(evidence, dict) and evidence.get("matched") is True
            ]
            confirmed_signals = [
                key
                for key in matched_signals
                if signal_evidence[key].get("confidence", "confirmed") == "confirmed"
            ]
            possible_signals = [
                key for key in matched_signals if key not in confirmed_signals
            ]
            selected_signals = list(signal_evidence)
            if selected_signals and not matched_signals:
                continue
            lead = self.leads.create_from_existing_match(
                campaign_id=campaign.id,
                product_id=campaign.product_id,
                result=row,
            )
            qualified = bool(matched_signals)
            rank_score = float(
                profile_match.get("matched_signal_count")
                or len(matched_signals)
            )
            positive_signals = [
                _profile_signal_evidence(key, signal_evidence[key])
                for key in matched_signals
            ]
            lead = self.leads.attach_qualification(
                lead.id,
                QualificationResult(
                    qualified=qualified,
                    fit_status=(
                        AgentFitStatus.GOOD_FIT
                        if confirmed_signals
                        else AgentFitStatus.MAYBE
                    ),
                    score=(
                        min(100, 70 + max(0, len(confirmed_signals) - 1) * 10)
                        if confirmed_signals
                        else 55
                        if possible_signals
                        else 50
                    ),
                    rationale=(
                        f"Confirmed selected signals: {', '.join(confirmed_signals)}."
                        if confirmed_signals
                        else f"Possible selected signals: {', '.join(possible_signals)}."
                        if possible_signals
                        else "Matched the audience trade and location; no opportunity signal was requested."
                    ),
                    positive_signals=positive_signals,
                    recommended_next_step="Review the stored evidence before outreach.",
                    signal_tags=matched_signals,
                ),
            )
            lead.rank_score = rank_score
            created.append(LeadRead.model_validate(lead))
        self.session.commit()
        return created

    def materialize_index_candidates(
        self,
        campaign_id: str,
        rows: list[dict[str, Any]],
    ) -> list[LeadRead]:
        """Materialize matched and unresolved index candidates into the same run."""
        self.materialize_existing_matches(campaign_id, rows)
        by_business_id = {
            lead.business_id: lead
            for lead in self.leads.list_by_campaign(campaign_id)
            if lead.business_id
        }
        synced: list[LeadRead] = []
        for row in rows:
            business_id = (row.get("raw") or {}).get("canonical_business_id")
            lead = by_business_id.get(business_id)
            if lead is not None:
                synced.append(
                    LeadRead.model_validate(self.leads.sync_search_match(lead.id, row))
                )
        return synced

    def reject_absent_index_candidates(
        self,
        campaign_id: str,
        *,
        selected_business_ids: set[str],
    ) -> None:
        for lead in self.leads.list_by_campaign(campaign_id):
            if lead.business_id and lead.business_id not in selected_business_ids:
                self.leads.mark_search_not_matched(
                    lead.id,
                    reason="Current evidence does not satisfy the saved search contract.",
                )

    def update(self, campaign_id: str, update: CampaignUpdate) -> CampaignModel:
        return self.campaigns.update(campaign_id, update)

    def delete(self, campaign_id: str) -> None:
        self.campaigns.delete(campaign_id)

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

    @staticmethod
    def _indexed_cached_rows(*, rows: list[dict[str, Any]]):
        indexed = []
        for row in rows:
            search_result = SearchResult.model_validate(row)
            indexed.append((row, search_result))
        return indexed

    def _create_existing_match_listing(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        indexed_rows,
    ) -> list[LeadRead]:
        discovered: list[LeadRead] = []
        for row, search_result in indexed_rows:
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
                    candidate_type=DiscoveryCandidateType.TARGET_BUSINESS,
                    confidence=100,
                    rejection_reason=None,
                )
            )
            if len(discovered) >= campaign.max_leads:
                continue
            lead = self.leads.create_from_existing_match(
                campaign_id=campaign.id,
                product_id=product.id,
                result=row,
            )
            self.discovery_candidates.mark_promoted(candidate.id, lead.id)
            lead = self.leads.attach_research(
                lead.id,
                build_cached_lead_research(
                    product=product,
                    lead=LeadRead.model_validate(lead),
                    row=row,
                    confidence=100,
                ),
            )
            lead = self.leads.attach_qualification(
                lead.id,
                score_cached_lead(
                    product=product,
                    lead=LeadRead.model_validate(lead),
                    row=row,
                    confidence=100,
                    signal_vocabulary=self.leads.signal_vocabulary_for_lead(lead.id),
                ),
            )
            discovered.append(LeadRead.model_validate(lead))

        self.memory.create_observation(
            CampaignMemoryCreate(
                product_id=product.id,
                campaign_id=campaign.id,
                type=ObservationType.LEAD_QUALITY,
                content=f"Business index produced {len(discovered)} existing matches.",
                tags=["discovery", "business_index", product.target_customer],
            )
        )
        return discovered

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

def _profile_signal_evidence(signal_key: str, evidence: Any) -> str:
    if not isinstance(evidence, dict):
        return signal_key
    fact_key = str(evidence.get("fact_key") or signal_key)
    value = evidence.get("value")
    if isinstance(value, bool):
        rendered_value = str(value).lower()
    elif value is None:
        rendered_value = "unknown"
    else:
        rendered_value = str(value)
    return f"{signal_key}: {fact_key}={rendered_value}"


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
