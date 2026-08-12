from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from agents.llm import HeuristicLLMClient, LLMClient, RemoteJsonLLMClient
from db.session import Database
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.search import SearchTool


@dataclass(slots=True)
class AppServices:
    settings: Settings
    db: Database
    llm: LLMClient
    search: SearchTool
    browser: DirectHttpBrowserTool
    email: EmailTool


def create_app_services(settings: Settings) -> AppServices:
    llm: LLMClient
    if settings.llm_json_endpoint:
        llm = RemoteJsonLLMClient(
            endpoint=settings.llm_json_endpoint,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    else:
        llm = HeuristicLLMClient()

    return AppServices(
        settings=settings,
        db=Database(settings.database_url),
        llm=llm,
        search=SearchTool(
            endpoint=settings.search_api_endpoint,
            api_key=settings.search_api_key,
            timeout_seconds=settings.request_timeout_seconds,
        ),
        browser=DirectHttpBrowserTool(timeout_seconds=settings.request_timeout_seconds),
        email=EmailTool(
            endpoint=settings.email_provider_endpoint,
            api_key=settings.email_api_key,
        ),
    )


def get_services(request: Request) -> AppServices:
    return request.app.state.services


def get_session(services: Annotated[AppServices, Depends(get_services)]) -> Session:
    generator = services.db.session()
    session = next(generator)
    try:
        yield session
    finally:
        generator.close()


DbSession = Annotated[Session, Depends(get_session)]
