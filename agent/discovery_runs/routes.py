from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from agent_runs.schemas import AgentRunCreate, AgentRunDetail, AgentRunRead, CampaignTrace
from agent_runs.service import AgentRunService
from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from app.service_factory import campaign_service
from campaign_sources.repository import CampaignSourceRepository
from campaign_sources.schemas import CampaignSourceRead
from campaigns.repository import CampaignRepository
from campaigns.schemas import (
    CampaignCreate,
    CampaignPreflightRead,
    CampaignRead,
    CampaignRunSummary,
    CampaignUpdate,
    LeadSeedInput,
)
from campaigns.service import CampaignService
from discovery.repository import DiscoveryCandidateRepository
from discovery.schemas import DiscoveryCandidateRead
from evaluation.schemas import CampaignMetrics
from insights.schemas import CampaignInsightRead
from insights.service import CampaignInsightService
from leads.repository import LeadRepository
from leads.export import leads_csv
from leads.selection import select_campaign_results
from leads.schemas import LeadRead
from messages.repository import MessageRepository
from messages.schemas import (
    CampaignMessageApproval,
    CampaignMessageBatchResult,
    CampaignMessageSend,
    CampaignOutreachDraftCreate,
    MessageRead,
)
from messages.service import MessageService
from products.repository import ProductRepository
from run_diagnostics.schemas import RunDiagnostics
from run_diagnostics.service import build_run_diagnostics
from shared.errors import ConflictError
from source_requests.schemas import (
    SourceProviderRead,
    SourceRequestCreate,
    SourceRequestRun,
)
from source_requests.catalog import build_source_catalog
from source_requests.service import SourceRequestService

router = APIRouter(prefix="/discovery-runs", tags=["discovery-runs"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
) -> CampaignService:
    return campaign_service(
        session=session,
        services=services,
        workspace_id=auth.workspace_id,
    )


@router.post("", response_model=CampaignRead)
def create_discovery_run(
    run: CampaignCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).create(run)


@router.post("/source-request", response_model=SourceRequestRun)
def create_source_request(
    request: SourceRequestCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _source_request_service(session, services, auth).create(request)


@router.post("/{run_id}/rerun", response_model=SourceRequestRun)
def rerun_source_request(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _source_request_service(session, services, auth).rerun(run_id)


def _source_request_service(
    session: DbSession,
    services: AppServices,
    auth: CurrentAuth,
) -> SourceRequestService:
    return SourceRequestService(
        products=ProductRepository(session, workspace_id=auth.workspace_id),
        campaigns=_service(session, services, auth),
        apify_source_provider_id=services.settings.apify_source_provider_id,
        apify_source_label=services.settings.apify_source_label,
        apify_sources=services.settings.apify_source_configs,
        google_places_configured=bool(services.settings.google_places_api_key),
        search_configured=services.search.is_configured,
        openstreetmap_enabled=services.settings.openstreetmap_enabled,
        source_recipes=services.settings.discovery_source_recipe_configs,
    )


@router.get("/source-providers", response_model=list[SourceProviderRead])
def list_source_providers(
    services: Annotated[AppServices, Depends(get_services)],
) -> list[SourceProviderRead]:
    settings = services.settings
    return [
        SourceProviderRead(
            id=source.id,
            label=source.label,
            configured=source.configured,
            detail=source.detail,
        )
        for source in build_source_catalog(
            google_places_configured=bool(settings.google_places_api_key),
            search_configured=services.search.is_configured,
            openstreetmap_enabled=settings.openstreetmap_enabled,
            apify_sources=settings.apify_source_configs,
        )
    ]

@router.get("", response_model=list[CampaignRead])
def list_discovery_runs(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).list()


@router.get("/{run_id}", response_model=CampaignRead)
def get_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).get(run_id)


@router.get("/{run_id}/export.csv")
def export_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    run = CampaignRead.model_validate(_service(session, services, auth).get(run_id))
    leads = [
        LeadRead.model_validate(lead)
        for lead in LeadRepository(session, workspace_id=auth.workspace_id).list_by_campaign(
            run_id
        )
    ]
    leads = select_campaign_results(run, leads)
    return Response(
        content=leads_csv(leads, scoutlead_path=f"/discovery-runs/{run_id}"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-contacts.csv"'},
    )


@router.patch("/{run_id}", response_model=CampaignRead)
def update_discovery_run(
    run_id: str,
    update: CampaignUpdate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).update(run_id, update)


@router.get("/{run_id}/sources", response_model=list[CampaignSourceRead])
def list_discovery_run_sources(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return CampaignSourceRepository(session).list_by_campaign(run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).delete(run_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{run_id}/pause", response_model=CampaignRead)
def pause_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).pause(run_id)


@router.post("/{run_id}/resume", response_model=CampaignRead)
def resume_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).resume(run_id)


@router.post("/{run_id}/run", response_model=CampaignRunSummary)
def run_discovery(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    service = _service(session, services, auth)
    _assert_preflight_ready(service.preflight(run_id))
    agent_run = AgentRunService(session).create(AgentRunCreate(campaign_id=run_id))
    return service.run_campaign(run_id, agent_run_id=agent_run.id)


@router.post("/{run_id}/enqueue", response_model=AgentRunRead)
def enqueue_discovery_run(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    service = _service(session, services, auth)
    _assert_preflight_ready(service.preflight(run_id))
    return AgentRunService(session).create(AgentRunCreate(campaign_id=run_id))


@router.get("/{run_id}/preflight", response_model=CampaignPreflightRead)
def discovery_run_preflight(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).preflight(run_id)


@router.get("/{run_id}/metrics", response_model=CampaignMetrics)
def discovery_run_metrics(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).metrics(run_id)


@router.get("/{run_id}/results", response_model=list[LeadRead])
def list_discovery_results(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    return _service(session, services, auth).results(run_id)


@router.get("/{run_id}/diagnostics", response_model=RunDiagnostics)
def get_discovery_run_diagnostics(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    service = _service(session, services, auth)
    run = CampaignRead.model_validate(service.get(run_id))
    results = [LeadRead.model_validate(result) for result in service.results(run_id)]
    return build_run_diagnostics(session, run=run, final_results=results)


@router.post("/{run_id}/results/seeds", response_model=list[LeadRead])
def add_discovery_seed_results(
    run_id: str,
    seeds: list[LeadSeedInput],
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    run = _service(session, services, auth).get(run_id)
    leads = LeadRepository(session, workspace_id=auth.workspace_id)
    return [leads.create_from_seed(run_id, run.product_id, seed) for seed in seeds]


@router.get("/{run_id}/discovery-candidates", response_model=list[DiscoveryCandidateRead])
def list_discovery_candidates(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return DiscoveryCandidateRepository(session).list_by_campaign(run_id)


@router.get("/{run_id}/messages", response_model=list[MessageRead])
def list_discovery_messages(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return MessageRepository(session, workspace_id=auth.workspace_id).list_by_campaign(run_id)


@router.post("/{run_id}/draft-shortlist", response_model=list[MessageRead])
def draft_discovery_shortlist(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return MessageService(
        session=session,
        email=services.email,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).create_outreach_drafts_for_run(run_id)


@router.post("/{run_id}/campaign-drafts", response_model=CampaignMessageBatchResult)
def create_discovery_campaign_drafts(
    run_id: str,
    draft: CampaignOutreachDraftCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return MessageService(
        session=session,
        email=services.email,
        workspace_id=auth.workspace_id,
    ).create_campaign_outreach_drafts(run_id, draft)


@router.post("/{run_id}/campaign-drafts/approve", response_model=CampaignMessageBatchResult)
def approve_discovery_campaign_drafts(
    run_id: str,
    approval: CampaignMessageApproval,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return MessageService(
        session=session,
        email=services.email,
        workspace_id=auth.workspace_id,
    ).approve_campaign_messages(run_id, approval)


@router.post("/{run_id}/campaign-drafts/send", response_model=CampaignMessageBatchResult)
def send_discovery_campaign_drafts(
    run_id: str,
    send: CampaignMessageSend,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return MessageService(
        session=session,
        email=services.email,
        workspace_id=auth.workspace_id,
    ).send_campaign_messages(run_id, send)


@router.get("/{run_id}/agent-runs", response_model=list[AgentRunRead])
def list_discovery_agent_runs(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return AgentRunService(session).list_by_campaign(run_id)


@router.get("/{run_id}/trace", response_model=CampaignTrace)
def get_discovery_trace(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return AgentRunService(session).trace_by_campaign(run_id)


@router.get("/{run_id}/insights", response_model=CampaignInsightRead)
def get_discovery_insights(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return CampaignInsightService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).latest(run_id)


@router.post("/{run_id}/insights", response_model=CampaignInsightRead)
def generate_discovery_insights(
    run_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    _service(session, services, auth).get(run_id)
    return CampaignInsightService(
        session=session,
        llm=services.llm,
        workspace_id=auth.workspace_id,
    ).generate(run_id)


def _assert_preflight_ready(preflight: CampaignPreflightRead) -> None:
    if preflight.ready:
        return
    failures = [check for check in preflight.checks if check.required and check.status == "failed"]
    raise ConflictError(
        "discovery run cannot start until required integrations are configured",
        {"failures": [failure.model_dump(mode="json") for failure in failures]},
    )
