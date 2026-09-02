import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.dependencies import create_app_services
from agent_runs.routes import router as agent_runs_router
from campaigns.routes import router as campaigns_router
from db.session import create_database
from discovery_runs.routes import router as discovery_runs_router
from email_connections.routes import router as email_connections_router
from insights.routes import router as insights_router
from leads.routes import router as leads_router
from messages.routes import router as messages_router
from products.routes import router as products_router
from shared.errors import SoutleadError
from shared.logger import configure_logging
from webhooks.routes import router as webhooks_router


class ApiAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str | None) -> None:
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.token or request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in {"/health", "/openapi.json"} or request.url.path.startswith(
            ("/docs", "/redoc")
        ):
            return await call_next(request)
        auth_header = request.headers.get("authorization", "")
        api_key_header = request.headers.get("x-api-key", "")
        expected = f"Bearer {self.token}"
        if auth_header != expected and api_key_header != self.token:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "valid API token required"}},
            )
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.services = create_app_services(settings)
    app.add_middleware(ApiAuthMiddleware, token=settings.api_auth_token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        if settings.auto_create_tables:
            create_database(app.state.services.db.engine)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.exception_handler(SoutleadError)
    async def handle_soutlead_error(request: Request, exc: SoutleadError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    app.include_router(products_router)
    app.include_router(agent_runs_router)
    app.include_router(campaigns_router)
    app.include_router(discovery_runs_router)
    app.include_router(email_connections_router)
    app.include_router(insights_router)
    app.include_router(leads_router)
    app.include_router(messages_router)
    app.include_router(webhooks_router)
    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
