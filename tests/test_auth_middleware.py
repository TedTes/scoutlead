from fastapi import FastAPI, Request
import anyio
import httpx

from app.config import Settings
from auth.middleware import AuthMiddleware


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware, settings=settings)

    @app.get("/private")
    def private(request: Request) -> dict:
        return {"service_account": request.state.auth_context.service_account}

    return app


def _get_private(settings: Settings, headers: dict[str, str] | None = None) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=_app(settings))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/private", headers=headers)

    return anyio.run(request)


def test_auth_middleware_allows_open_local_mode() -> None:
    response = _get_private(Settings(_env_file=None, require_user_auth=False))

    assert response.status_code == 200
    assert response.json() == {"service_account": False}


def test_auth_middleware_requires_clerk_session_when_enabled() -> None:
    response = _get_private(Settings(_env_file=None, require_user_auth=True))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_auth_middleware_accepts_service_token_when_user_auth_is_enabled() -> None:
    response = _get_private(
        Settings(_env_file=None, api_auth_token="service-token", require_user_auth=True),
        headers={"authorization": "Bearer service-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"service_account": True}


def test_auth_middleware_requires_service_token_when_configured_without_user_auth() -> None:
    missing_token_response = _get_private(
        Settings(_env_file=None, api_auth_token="service-token", require_user_auth=False)
    )
    token_response = _get_private(
        Settings(_env_file=None, api_auth_token="service-token", require_user_auth=False),
        headers={"x-api-key": "service-token"},
    )

    assert missing_token_response.status_code == 401
    assert missing_token_response.json()["error"] == {
        "code": "unauthorized",
        "message": "valid API token required",
    }
    assert token_response.status_code == 200
    assert token_response.json() == {"service_account": True}
