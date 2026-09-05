from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from auth.clerk import AuthConfigurationError, AuthError, ClerkTokenVerifier
from auth.context import AuthContext


EXEMPT_PATHS = {"/health", "/openapi.json", "/email/gmail/callback"}
EXEMPT_PREFIXES = ("/docs", "/redoc")


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:
        super().__init__(app)
        self.settings = settings
        self.verifier = ClerkTokenVerifier(settings)

    async def dispatch(self, request: Request, call_next):
        request.state.auth_context = AuthContext()
        if _is_exempt_request(request):
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        api_key_header = request.headers.get("x-api-key", "")
        if _matches_service_token(self.settings.api_auth_token, auth_header, api_key_header):
            request.state.auth_context = AuthContext(service_account=True)
            return await call_next(request)

        if not self.settings.require_user_auth and not self.settings.api_auth_token:
            return await call_next(request)

        if not self.settings.require_user_auth:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "valid API token required"}},
            )

        try:
            claims = await self.verifier.verify_authorization_header(auth_header)
        except AuthConfigurationError as exc:
            return JSONResponse(
                status_code=503,
                content={"error": {"code": "configuration_error", "message": str(exc)}},
            )
        except AuthError:
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "valid Clerk session required"}},
            )

        request.state.auth_context = AuthContext(
            user_id=claims.subject,
            workspace_id=claims.workspace_id,
            email=claims.email,
        )
        return await call_next(request)


def _is_exempt_request(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        or request.url.path in EXEMPT_PATHS
        or request.url.path.startswith(EXEMPT_PREFIXES)
    )


def _matches_service_token(token: str | None, auth_header: str, api_key_header: str) -> bool:
    if not token:
        return False
    return auth_header == f"Bearer {token}" or api_key_header == token
