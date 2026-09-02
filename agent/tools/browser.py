from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from shared.utils import normalize_text, truncate

EVIDENCE_LINK_RE = re.compile(r"(contact|quote|estimate|about|service|pricing|request)", re.I)
MAX_EVIDENCE_PAGES = 4


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
        primary = self._inspect_url(url)
        if primary.error:
            return primary

        pages = [primary]
        for link in _candidate_evidence_links(primary.links, primary.url):
            if len(pages) >= MAX_EVIDENCE_PAGES:
                break
            page = self._inspect_url(link)
            if not page.error:
                pages.append(page)

        if len(pages) == 1:
            return primary

        return WebsiteInspection(
            url=primary.url,
            title=primary.title,
            description=primary.description,
            text=truncate(normalize_text(" ".join(_page_text(page) for page in pages)), 9000),
            emails=sorted({email for page in pages for email in page.emails})[:10],
            links=sorted({link for page in pages for link in page.links})[:80],
        )

    def _inspect_url(self, url: str) -> WebsiteInspection:
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


def _candidate_evidence_links(links: list[str], base_url: str) -> list[str]:
    base_domain = _domain(base_url)
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for link in links:
        if not link.startswith(("http://", "https://")):
            continue
        if _domain(link) != base_domain:
            continue
        if link in seen or not EVIDENCE_LINK_RE.search(link):
            continue
        seen.add(link)
        ranked.append((_link_priority(link), link))
    return [link for _, link in sorted(ranked, key=lambda item: (item[0], item[1]))]


def _link_priority(link: str) -> int:
    path = urlparse(link).path.lower()
    if "contact" in path:
        return 0
    if "quote" in path or "estimate" in path or "request" in path:
        return 1
    if "about" in path:
        return 2
    if "service" in path:
        return 3
    return 4


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc or parsed.path).split(":", 1)[0].removeprefix("www.").lower()


def _page_text(page: WebsiteInspection) -> str:
    label = page.title or page.url
    return f"{label}. {page.description or ''} {page.text}"


class BrowserAutomationFallbackTool:
    def inspect(self, url: str) -> WebsiteInspection:
        return WebsiteInspection(
            url=url,
            error="browser automation is not configured in the initial implementation",
        )
