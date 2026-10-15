from fastapi import APIRouter, Request, status

from app.dependencies import CurrentAuth, DbSession
from demo_sites.schemas import DemoSiteRead, DemoSiteUpdate
from demo_sites.service import DemoSiteService

router = APIRouter(prefix="/demo-sites", tags=["demo-sites"])
public_router = APIRouter(prefix="/u/demo-sites", tags=["public-demo-sites"])


def _service(request: Request, session: DbSession, workspace_id: str | None) -> DemoSiteService:
    settings = request.app.state.services.settings
    provider = "openai" if settings.openai_api_key else "remote"
    model = settings.openai_model if settings.openai_api_key else settings.llm_model
    return DemoSiteService(session, llm=request.app.state.services.llm, workspace_id=workspace_id,
                           provider=provider, model=model)


@router.post("/from-result/{result_id}", response_model=DemoSiteRead, status_code=status.HTTP_201_CREATED)
def generate_demo(result_id: str, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).generate(result_id)


@router.get("/{demo_id}", response_model=DemoSiteRead)
def get_demo(demo_id: str, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).get(demo_id)


@router.patch("/{demo_id}", response_model=DemoSiteRead)
def update_demo(demo_id: str, data: DemoSiteUpdate, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).update(demo_id, data)


@router.post("/{demo_id}/publish", response_model=DemoSiteRead)
def publish_demo(demo_id: str, request: Request, session: DbSession, auth: CurrentAuth):
    return _service(request, session, auth.workspace_id).publish(demo_id)


@public_router.get("/{token}", response_model=DemoSiteRead)
def public_demo(token: str, request: Request, session: DbSession):
    return _service(request, session, None).public(token)
