from sqlalchemy.orm import Session

from app.dependencies import AppServices
from business_index.refresh import BusinessIndexRefreshService
from campaigns.service import CampaignService
from territories.opportunity_audit import BusinessOpportunityAuditor
from territories.refresh import TerritoryRefreshService
from tools.verify import EmailVerificationTool
from tools.source_registry import SourceAdapterRegistry


def campaign_service(
    *,
    session: Session,
    services: AppServices,
    workspace_id: str | None,
) -> CampaignService:
    settings = services.settings
    return CampaignService(
        session=session,
        llm=services.llm,
        search_tool=services.search,
        browser=services.browser,
        email=services.email,
        google_places_api_key=settings.google_places_api_key,
        google_places_api_endpoint=settings.google_places_api_endpoint,
        apify_api_token=settings.apify_api_token,
        apify_api_base_url=settings.apify_api_base_url,
        apify_source_provider_id=settings.apify_source_provider_id,
        apify_actor_id=settings.apify_actor_id,
        apify_actor_input_template=settings.apify_actor_input_template,
        apify_actor_result_mapping=settings.apify_actor_result_mapping,
        apify_actor_max_charge_usd=settings.apify_actor_max_charge_usd,
        apify_sources=settings.apify_source_configs,
        contact_verification_provider=settings.contact_verification_provider,
        email_verification_endpoint=settings.email_verification_endpoint,
        email_verification_api_key=settings.email_verification_api_key,
        bouncer_api_key=settings.bouncer_api_key,
        bouncer_api_endpoint=settings.bouncer_api_endpoint,
        zerobounce_api_key=settings.zerobounce_api_key,
        zerobounce_api_endpoint=settings.zerobounce_api_endpoint,
        embedding=services.embedding,
        semantic_cache_min_score=settings.semantic_cache_min_score,
        semantic_cache_min_results=settings.semantic_cache_min_results,
        timeout_seconds=settings.request_timeout_seconds,
        workspace_id=workspace_id,
        opportunity_auditor=BusinessOpportunityAuditor(
            session=session,
            verifier=_verification_tool(services),
            search=services.search,
            timeout_seconds=settings.request_timeout_seconds,
        ),
    )


def territory_refresh_service(
    *,
    session: Session,
    services: AppServices,
    workspace_id: str,
) -> TerritoryRefreshService:
    settings = services.settings
    return TerritoryRefreshService(
        session=session,
        campaigns=campaign_service(
            session=session,
            services=services,
            workspace_id=workspace_id,
        ),
        workspace_id=workspace_id,
        llm=services.llm,
        opportunity_auditor=BusinessOpportunityAuditor(
            session=session,
            verifier=_verification_tool(services),
            search=services.search,
            timeout_seconds=settings.request_timeout_seconds,
        ),
    )


def business_index_refresh_service(
    *,
    session: Session,
    services: AppServices,
) -> BusinessIndexRefreshService:
    settings = services.settings
    return BusinessIndexRefreshService(
        session=session,
        registry=SourceAdapterRegistry(
            search_tool=services.search,
            google_places_api_key=settings.google_places_api_key,
            google_places_api_endpoint=settings.google_places_api_endpoint,
            apify_api_token=settings.apify_api_token,
            apify_api_base_url=settings.apify_api_base_url,
            apify_source_provider_id=settings.apify_source_provider_id,
            apify_actor_id=settings.apify_actor_id,
            apify_actor_input_template=settings.apify_actor_input_template,
            apify_actor_result_mapping=settings.apify_actor_result_mapping,
            apify_actor_max_charge_usd=settings.apify_actor_max_charge_usd,
            apify_sources=settings.apify_source_configs,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        campaigns=campaign_service(session=session, services=services, workspace_id=None),
        auditor=BusinessOpportunityAuditor(
            session=session,
            verifier=_verification_tool(services),
            search=services.search,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        embedding=services.embedding,
        discovery_config={
            "google_places_configured": bool(settings.google_places_api_key),
            "search_configured": services.search.is_configured,
            "openstreetmap_enabled": settings.openstreetmap_enabled,
            "apify_sources": settings.apify_source_configs,
            "source_recipes": settings.discovery_source_recipe_configs,
        },
    )


def _verification_tool(services: AppServices) -> EmailVerificationTool:
    settings = services.settings
    return EmailVerificationTool(
        provider=settings.contact_verification_provider,
        endpoint=settings.email_verification_endpoint,
        api_key=settings.email_verification_api_key,
        bouncer_api_key=settings.bouncer_api_key,
        bouncer_api_endpoint=settings.bouncer_api_endpoint,
        zerobounce_api_key=settings.zerobounce_api_key,
        zerobounce_api_endpoint=settings.zerobounce_api_endpoint,
        timeout_seconds=settings.request_timeout_seconds,
    )
