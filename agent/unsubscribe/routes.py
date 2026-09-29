from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.config import Settings, get_settings
from app.dependencies import DbSession
from unsubscribe.service import UnsubscribeService


router = APIRouter(tags=["unsubscribe"])


@router.get("/u/{token}", response_class=HTMLResponse)
def confirm_unsubscribe(
    token: str,
    session: DbSession,
    settings: Settings = Depends(get_settings),
):
    UnsubscribeService(session, signing_secret=settings.unsubscribe_signing_secret).claims(token)
    return HTMLResponse(
        "<!doctype html><html><body><main><h1>Unsubscribe</h1>"
        "<p>Confirm that you no longer want outreach from this sender.</p>"
        f'<form method="post" action="/u/{token}"><button type="submit">Unsubscribe</button></form>'
        "</main></body></html>"
    )


@router.post("/u/{token}", response_class=HTMLResponse)
def unsubscribe(
    token: str,
    session: DbSession,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    del request
    UnsubscribeService(session, signing_secret=settings.unsubscribe_signing_secret).unsubscribe(
        token
    )
    return HTMLResponse(
        "<!doctype html><html><body><main><h1>Unsubscribed</h1>"
        "<p>You will not receive further outreach from this sender.</p>"
        "</main></body></html>"
    )
