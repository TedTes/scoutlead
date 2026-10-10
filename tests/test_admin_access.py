import asyncio
from types import SimpleNamespace

import httpx

from app import dependencies
from app.config import Settings
from auth.context import AuthContext


def test_clerk_primary_email_uses_primary_address() -> None:
    payload = {
        "primary_email_address_id": "idn_primary",
        "email_addresses": [
            {"id": "idn_other", "email_address": "other@example.com"},
            {"id": "idn_primary", "email_address": " Admin@Example.com "},
        ],
    }

    assert dependencies._primary_email_from_clerk_user(payload) == "admin@example.com"


def test_clerk_primary_email_fetches_verified_user() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/users/user_admin"
        assert request.headers["authorization"] == "Bearer clerk-secret"
        return httpx.Response(
            200,
            json={
                "primary_email_address_id": "idn_primary",
                "email_addresses": [
                    {"id": "idn_primary", "email_address": "admin@example.com"}
                ],
            },
        )

    dependencies._admin_email_cache.clear()
    email = asyncio.run(
        dependencies._clerk_primary_email(
            "user_admin",
            "clerk-secret",
            transport=httpx.MockTransport(handler),
        )
    )

    assert email == "admin@example.com"


def test_require_admin_resolves_missing_token_email(monkeypatch) -> None:
    async def resolved_email(*args, **kwargs):
        return "admin@example.com"

    monkeypatch.setattr(dependencies, "_clerk_primary_email", resolved_email)
    services = SimpleNamespace(
        settings=Settings(
            _env_file=None,
            environment="production",
            require_user_auth=True,
            clerk_secret_key="clerk-secret",
            admin_emails="admin@example.com",
        )
    )

    result = asyncio.run(
        dependencies.require_admin(AuthContext(user_id="user_admin"), services)
    )

    assert result.email == "admin@example.com"
