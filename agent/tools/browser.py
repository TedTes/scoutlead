from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from shared.utils import normalize_text, truncate


class WebsiteInspection(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    text: str = ""
    emails: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    error: str | None = None


class BrowserToolProtocol(Protocol):
    def inspect(self, url: str) -> WebsiteInspection:
        raise NotImplementedError


class DirectHttpBrowserTool:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def inspect(self, url: str) -> WebsiteInspection:
        try:
            response = httpx.get(
                url,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"user-agent": "soutlead/0.1 customer-discovery research"},
            )
            response.raise_for_status()
        except Exception as exc:
            return WebsiteInspection(url=url, error=str(exc))

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = normalize_text(soup.title.string if soup.title else None) or None
        description = None
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = normalize_text(str(meta["content"]))
        text = truncate(normalize_text(soup.get_text(" ")), 5000)
        emails = sorted(set(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", response.text, re.I)))
        links = []
        for link in soup.find_all("a", href=True):
            links.append(urljoin(str(response.url), str(link["href"])))
        return WebsiteInspection(
            url=str(response.url),
            title=title,
            description=description,
            text=text,
            emails=emails[:10],
            links=sorted(set(links))[:50],
        )


class BrowserAutomationFallbackTool:
    def inspect(self, url: str) -> WebsiteInspection:
        return WebsiteInspection(
            url=url,
            error="browser automation is not configured in the initial implementation",
        )
