from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import Settings
from agents.embeddings import EmbeddingClient, MissingEmbeddingClient, OpenAIEmbeddingClient
from agents.llm import (
    LLMClient,
    MissingLLMClient,
    OpenAIStructuredLLMClient,
    RemoteJsonLLMClient,
)
from db.session import Database
from tools.browser import DirectHttpBrowserTool
from tools.email import EmailTool
from tools.search import SearchTool


@dataclass(slots=True)
class AppServices:
    settings: Settings
    db: Database
    llm: LLMClient
    embedding: EmbeddingClient
    search: SearchTool
    browser: DirectHttpBrowserTool
    email: EmailTool


def create_app_services(settings: Settings) -> AppServices:
    llm: LLMClient
    if settings.openai_api_key:
        llm = OpenAIStructuredLLMClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    elif settings.llm_json_endpoint:
        llm = RemoteJsonLLMClient(
            endpoint=settings.llm_json_endpoint,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.request_timeout_seconds,
        )
    else:
        llm = MissingLLMClient()

    embedding: EmbeddingClient
    if settings.openai_api_key:
        embedding = OpenAIEmbeddingClient(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
            dimension=settings.embedding_dimension,
            timeout_seconds=settings.request_timeout_seconds,
        )
    else:
        embedding = MissingEmbeddingClient(
            model=settings.openai_embedding_model,
            dimension=settings.embedding_dimension,
        )

    return AppServices(
        settings=settings,
        db=Database(settings.database_url),
        llm=llm,
        embedding=embedding,
        search=SearchTool(
            endpoint=settings.search_api_endpoint,
            api_key=settings.search_api_key,
            provider=settings.search_provider,
            timeout_seconds=settings.request_timeout_seconds,
            require_config=settings.require_real_search or settings.strict_external_providers,
        ),
        browser=DirectHttpBrowserTool(timeout_seconds=settings.request_timeout_seconds),
        email=EmailTool(
            provider=settings.email_provider,
            endpoint=settings.email_provider_endpoint,
            api_key=settings.email_api_key,
            resend_api_key=settings.resend_api_key,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
            reply_to=settings.email_reply_to,
            google_oauth_client_id=settings.google_oauth_client_id,
            google_oauth_client_secret=settings.google_oauth_client_secret,
            google_oauth_token_url=settings.google_oauth_token_url,
            google_token_encryption_key=settings.google_token_encryption_key,
            gmail_api_base_url=settings.gmail_api_base_url,
            timeout_seconds=settings.request_timeout_seconds,
            allow_console=not (settings.require_real_email or settings.strict_external_providers),
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
