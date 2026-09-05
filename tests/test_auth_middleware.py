from fastapi import FastAPI, Request
import httpx
import pytest

from app.config import Settings
from auth.middleware import AuthMiddleware


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, settings=settings)

    @app.get("/private")
    def private(request: Request) -> dict:
        return {"service_account": request.state.auth_context.service_account}

    return app


@pytest.mark.asyncio
async def test_auth_middleware_allows_open_local_mode() -> None:
    transport = httpx.ASGITransport(app=_app(Settings(_env_file=None, require_user_auth=False)))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/private")

        assert response.status_code == 200
        assert response.json() == {"service_account": False}


@pytest.mark.asyncio
async def test_auth_middleware_requires_clerk_session_when_enabled() -> None:
    transport = httpx.ASGITransport(app=_app(Settings(_env_file=None, require_user_auth=True)))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/private")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_auth_middleware_accepts_service_token_when_user_auth_is_enabled() -> None:
    transport = httpx.ASGITransport(
        app=_app(Settings(_env_file=None, api_auth_token="service-token", require_user_auth=True))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/private", headers={"authorization": "Bearer service-token"})

        assert response.status_code == 200
        assert response.json() == {"service_account": True}


@pytest.mark.asyncio
async def test_auth_middleware_requires_service_token_when_configured_without_user_auth() -> None:
    transport = httpx.ASGITransport(
        app=_app(Settings(_env_file=None, api_auth_token="service-token", require_user_auth=False))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        missing_token_response = await client.get("/private")
        token_response = await client.get("/private", headers={"x-api-key": "service-token"})

        assert missing_token_response.status_code == 401
        assert missing_token_response.json()["error"] == {
            "code": "unauthorized",
            "message": "valid API token required",
        }
        assert token_response.status_code == 200
        assert token_response.json() == {"service_account": True}
