from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from app.dependencies import AppServices, CurrentAuth, DbSession, get_services
from email_connections.service import GmailAuthorizationUrl, GmailConnectionStatus, GmailOAuthService
from products.repository import ProductRepository
from shared.errors import SoutleadError

router = APIRouter(tags=["email-connections"])


def _service(
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
) -> GmailOAuthService:
    return GmailOAuthService(session=session, settings=services.settings)


def _scoped_service(session: DbSession, services: AppServices, auth: CurrentAuth) -> GmailOAuthService:
    return GmailOAuthService(
        session=session,
        settings=services.settings,
        workspace_id=auth.workspace_id,
    )


@router.get(
    "/products/{product_id}/email/gmail/status",
    response_model=GmailConnectionStatus,
)
def gmail_status(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    ProductRepository(session, workspace_id=auth.workspace_id).get(product_id)
    return _scoped_service(session, services, auth).status(product_id)


@router.get(
    "/products/{product_id}/email/gmail/connect",
    response_model=GmailAuthorizationUrl,
)
def gmail_connect(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    ProductRepository(session, workspace_id=auth.workspace_id).get(product_id)
    return _scoped_service(session, services, auth).authorization_url(product_id)


@router.delete(
    "/products/{product_id}/email/gmail",
    response_model=GmailConnectionStatus,
)
def gmail_disconnect(
    product_id: str,
    session: DbSession,
    services: Annotated[AppServices, Depends(get_services)],
    auth: CurrentAuth,
):
    ProductRepository(session, workspace_id=auth.workspace_id).get(product_id)
    return _scoped_service(session, services, auth).disconnect(product_id)


@router.get("/email/gmail/callback", response_class=HTMLResponse)
def gmail_callback(
    service: Annotated[GmailOAuthService, Depends(_service)],
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error:
        return HTMLResponse(
            _callback_html(False, f"Gmail connection failed: {error}"),
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(_callback_html(False, "Gmail connection is missing OAuth data."), status_code=400)
    try:
        connection = service.complete_oauth(code=code, state=state)
    except SoutleadError as exc:
        return HTMLResponse(_callback_html(False, exc.message), status_code=exc.status_code)
    return HTMLResponse(
        _callback_html(True, f"Gmail connected for {connection.email_address}."),
        status_code=200,
    )


def _callback_html(success: bool, message: str) -> str:
    status = "connected" if success else "failed"
    escaped_message = (
        message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Gmail {status}</title>
    <style>
      body {{
        font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f6f7f8;
        color: #1a1d21;
      }}
      main {{
        width: min(420px, calc(100vw - 40px));
        border: 1px solid #d9dde3;
        border-radius: 14px;
        background: #fff;
        padding: 24px;
        box-shadow: 0 20px 60px rgba(15, 23, 42, .10);
      }}
      h1 {{ font-size: 18px; margin: 0 0 8px; }}
      p {{ color: #56606b; margin: 0; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Gmail {status}</h1>
      <p>{escaped_message}</p>
    </main>
    <script>
      if (window.opener) {{
        window.opener.postMessage({{ type: "scoutlead:gmail:{status}" }}, "*");
        window.setTimeout(() => window.close(), 600);
      }}
    </script>
  </body>
</html>"""
