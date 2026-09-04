from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from agent_runs.schemas import AgentRunCreate
from agent_runs.service import AgentRunService
from app.dependencies import AppServices, DbSession, get_services
from campaigns.schemas import CampaignCreate, CampaignRunSummary
from campaigns.service import CampaignService
from products.schemas import (
    ProductCreate,
    ProductDescriptionCreate,
    ProductDiscoveryStart,
    ProductRead,
    ProductUpdate,
)
from products.discovery_policy import (
    normalize_places_region_code,
    validate_google_places_query,
)
from products.service import ProductService
from shared.utils import utcnow

router = APIRouter(prefix="/products", tags=["products"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> ProductService:
    return ProductService(
        session,
        llm=services.llm,
        browser=services.browser,
        search=services.search,
    )


def _campaign_service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> CampaignService:
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
        apify_sources=services.settings.apify_source_configs,
        contact_verification_provider=services.settings.contact_verification_provider,
        email_verification_endpoint=services.settings.email_verification_endpoint,
        email_verification_api_key=services.settings.email_verification_api_key,
        bouncer_api_key=services.settings.bouncer_api_key,
        bouncer_api_endpoint=services.settings.bouncer_api_endpoint,
        zerobounce_api_key=services.settings.zerobounce_api_key,
        zerobounce_api_endpoint=services.settings.zerobounce_api_endpoint,
        embedding=services.embedding,
        semantic_cache_min_score=services.settings.semantic_cache_min_score,
        semantic_cache_min_results=services.settings.semantic_cache_min_results,
        timeout_seconds=services.settings.request_timeout_seconds,
    )


@router.post("", response_model=ProductRead)
def create_product(
    product: ProductCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create(product)


@router.post("/from-description", response_model=ProductRead)
def create_product_from_description(
    request: ProductDescriptionCreate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).create_from_description(request)


@router.post("/{product_id}/discover", response_model=CampaignRunSummary)
def start_product_discovery(
    product_id: str,
    request: ProductDiscoveryStart,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    product_service = _service(session, services)
    plan = product_service.plan_discovery(product_id)
    validate_google_places_query(plan.discovery_query)
    product = ProductRead.model_validate(product_service.apply_discovery_plan(product_id, plan))
    campaign_service = _campaign_service(session, services)
    region_code = normalize_places_region_code(plan.region_code) or normalize_places_region_code(
        plan.target_geography
    )
    source_selection_reason = (
        "Product discovery uses the precise local-business discovery source and does not "
        "fall back to broad web search."
    )
    run = campaign_service.create(
        CampaignCreate(
            product_id=product.id,
            name=f"{product.product_name} discovery {utcnow().strftime('%Y-%m-%d %H:%M')}",
            source_preset_id="google-places-local-business",
            source_input=plan.discovery_query,
            source_inputs={
                key: value
                for key, value in {
                    "region_code": region_code,
                    "source_selection": "google_places_local_business",
                    "source_selection_reason": source_selection_reason,
                }.items()
                if value
            },
            max_leads=request.max_results,
            channels=["email"],
        )
    )
    agent_run = AgentRunService(session).create(AgentRunCreate(campaign_id=run.id))
    return campaign_service.run_campaign(run.id, agent_run_id=agent_run.id)


@router.get("", response_model=list[ProductRead])
def list_products(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).list()


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).get(product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: str,
    update: ProductUpdate,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    return _service(session, services).update(product_id, update)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
):
    _service(session, services).delete(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
