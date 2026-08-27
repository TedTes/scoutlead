from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from agent_runs.schemas import AgentRunCreate, AgentRunDetail, AgentRunRead, CampaignTrace
from agent_runs.service import AgentRunService
from app.dependencies import AppServices, DbSession, get_services
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead
from campaigns.repository import CampaignRepository
from campaigns.schemas import CampaignCreate, CampaignPreflightRead, CampaignRead, CampaignRunSummary, LeadSeedInput
from campaigns.service import CampaignService
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateRead
from evaluation.schemas import CampaignMetrics
from insights.schemas import CampaignInsightRead
from insights.service import CampaignInsightService
from leads.repository import LeadRepository
from leads.schemas import LeadRead
from messages.repository import MessageRepository
from messages.schemas import MessageRead
from products.repository import ProductRepository
from shared.errors import ConflictError
from source_requests.schemas import (
    GOOGLE_PLACES_PROVIDER_ID,
    SourceProviderRead,
    SourceRequestCreate,
    SourceRequestRun,
)
from source_requests.service import SourceRequestService

router = APIRouter(prefix="/discovery-runs", tags=["discovery-runs"])


def _service(session: DbSession, services: Annotated[AppServices, Depends(get_services)]) -> CampaignService:
    return CampaignService(
        session=session,
        llm=services.llm,
        search_tool=services.search,
        browser=services.browser,
        email=services.email,
        google_places_api_key=services.settings.google_places_api_key,
        google_places_api_endpoint=services.settings.google_places_api_endpoint,
        apify_api_token=services.settings.apify_api_token,
        apify_api_base_url=services.settings.apify_api_base_url,
        apify_source_provider_id=services.settings.apify_source_provider_id,
        apify_actor_id=services.settings.apify_actor_id,
        apify_actor_input_template=services.settings.apify_actor_input_template,
        apify_actor_result_mapping=services.settings.apify_actor_result_mapping,
        apify_actor_max_charge_usd=services.settings.apify_actor_max_charge_usd,
        timeout_seconds=services.settings.request_timeout_seconds,
    )


@router.post("", response_model=CampaignRead)
def create_discovery_run(
    run: CampaignCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create(run)


@router.post("/source-request", response_model=SourceRequestRun)
def create_source_request(
    request: SourceRequestCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return SourceRequestService(
        products=ProductRepository(session),
        campaigns=_service(session, services),
        agent_runs=AgentRunService(session),
        apify_source_provider_id=services.settings.apify_source_provider_id,
        apify_source_label=services.settings.apify_source_label,
    ).create(request)


@router.get("/source-providers", response_model=list[SourceProviderRead])
def list_source_providers(
    services: Annotated[AppServices, Depends(get_services)],
) -> list[SourceProviderRead]:
    settings = services.settings
    providers = [
        SourceProviderRead(
            id=GOOGLE_PLACES_PROVIDER_ID,
            label="Google Places",
            configured=bool(settings.google_places_api_key),
            detail="Local business discovery",
        )
    ]
    if settings.apify_source_provider_id:
        providers.append(
            SourceProviderRead(
                id=settings.apify_source_provider_id,
                label=settings.apify_source_label,
                configured=bool(settings.apify_api_token and settings.apify_actor_id),
                detail=f"{settings.apify_source_label} listings",
            )
        )
    return providers


@router.get("", response_model=list[CampaignRead])
def list_discovery_runs(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).list()


@router.get("/{run_id}", response_model=CampaignRead)
def get_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).get(run_id)


@router.get("/{run_id}/sources", response_model=list[CampaignSourceRead])
def list_discovery_run_sources(run_id: str, session: DbSession):
    return CampaignSourceRepository(session).list_by_campaign(run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    _service(session, services).delete(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{run_id}/pause", response_model=CampaignRead)
def pause_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).pause(run_id)


@router.post("/{run_id}/resume", response_model=CampaignRead)
def resume_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).resume(run_id)


@router.post("/{run_id}/run", response_model=CampaignRunSummary)
def run_discovery(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    service = _service(session, services)
    _assert_preflight_ready(service.preflight(run_id))
    agent_run = AgentRunService(session).create(AgentRunCreate(campaign_id=run_id))
    return service.run_campaign(run_id, agent_run_id=agent_run.id)


@router.post("/{run_id}/enqueue", response_model=AgentRunRead)
def enqueue_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    service = _service(session, services)
    _assert_preflight_ready(service.preflight(run_id))
    return AgentRunService(session).create(AgentRunCreate(campaign_id=run_id))


@router.get("/{run_id}/preflight", response_model=CampaignPreflightRead)
def discovery_run_preflight(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).preflight(run_id)


@router.get("/{run_id}/metrics", response_model=CampaignMetrics)
def discovery_run_metrics(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).metrics(run_id)


@router.get("/{run_id}/results", response_model=list[LeadRead])
def list_discovery_results(run_id: str, session: DbSession):
    return LeadRepository(session).list_by_campaign(run_id)


@router.post("/{run_id}/results/seeds", response_model=list[LeadRead])
def add_discovery_seed_results(run_id: str, seeds: list[LeadSeedInput], session: DbSession):
    run = CampaignRepository(session).get(run_id)
    leads = LeadRepository(session)
    return [leads.create_from_seed(run_id, run.product_id, seed) for seed in seeds]


@router.get("/{run_id}/discovery-candidates", response_model=list[DiscoveryCandidateRead])
def list_discovery_candidates(run_id: str, session: DbSession):
    return DiscoveryCandidateRepository(session).list_by_campaign(run_id)


@router.get("/{run_id}/messages", response_model=list[MessageRead])
def list_discovery_messages(run_id: str, session: DbSession):
    return MessageRepository(session).list_by_campaign(run_id)


@router.get("/{run_id}/agent-runs", response_model=list[AgentRunRead])
def list_discovery_agent_runs(run_id: str, session: DbSession):
    return AgentRunService(session).list_by_campaign(run_id)


@router.get("/{run_id}/trace", response_model=CampaignTrace)
def get_discovery_trace(run_id: str, session: DbSession):
    return AgentRunService(session).trace_by_campaign(run_id)


@router.get("/{run_id}/insights", response_model=CampaignInsightRead)
def get_discovery_insights(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return CampaignInsightService(session=session, llm=services.llm).latest(run_id)


@router.post("/{run_id}/insights", response_model=CampaignInsightRead)
def generate_discovery_insights(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return CampaignInsightService(session=session, llm=services.llm).generate(run_id)


def _assert_preflight_ready(preflight: CampaignPreflightRead) -> None:
    if preflight.ready:
        return
    failures = [check for check in preflight.checks if check.required and check.status == "failed"]
    raise ConflictError(
        "discovery run cannot start until required integrations are configured",
        {"failures": [failure.model_dump(mode="json") for failure in failures]},
    )
