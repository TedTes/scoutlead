from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib.parse import urlencode, urlparse

import httpx
from pydantic import BaseModel

from campaigns.schemas import CampaignRead
from products.schemas import DiscoverySource, DiscoverySourceType, ProductRead
from shared.errors import ConfigurationError


class SearchResult(BaseModel):
    title: str
    url: str | None = None
    snippet: str | None = None
    geography: str | None = None
    contact_email: str | None = None
    source: str = "search"
    raw: dict[str, Any] = {}


class SearchToolProtocol(Protocol):
    def search(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        source: DiscoverySource,
        limit: int,
        query: str | None = None,
    ) -> list[SearchResult]:
        raise NotImplementedError


class SearchTool:
    name = "search"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        provider: str = "generic",
        timeout_seconds: float = 20.0,
        require_config: bool = False,
    ) -> None:
        self.endpoint = endpoint
        self.api_key = api_key
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.require_config = require_config

    @property
    def is_configured(self) -> bool:
        if self.provider in {"tavily", "brave"}:
            return bool(self.api_key)
        return bool(self.endpoint)

    def execute(self, args: dict[str, Any]) -> list[dict[str, Any]]:
        product = ProductRead.model_validate(args["product"])
        campaign = CampaignRead.model_validate(args["campaign"])
        source = DiscoverySource.model_validate(args["source"])
        limit = int(args["limit"])
        query = str(args.get("resolved_query") or "").strip() or None
        return [
            result.model_dump(mode="json")
            for result in self.search(
                product=product,
                campaign=campaign,
                source=source,
                limit=limit,
                query=query,
            )
        ]

    def lookup(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.is_configured:
            if self.require_config:
                raise ConfigurationError(
                    "real search provider is required for source lookup",
                    {"provider": self.provider},
                )
            return []

        source = DiscoverySource(type=DiscoverySourceType.WEB_SEARCH, value=query)
        if self.provider == "tavily":
            return self._search_tavily(query, source, limit)
        if self.provider == "brave":
            return self._search_brave(query, limit)
        return self._lookup_generic(query, limit)

    def search(
        self,
        *,
        product: ProductRead,
        campaign: CampaignRead,
        source: DiscoverySource,
        limit: int,
        query: str | None = None,
    ) -> list[SearchResult]:
        if source.type == DiscoverySourceType.SEED:
            return [self._parse_seed(source.value, product.target_geography)]

        if not self.is_configured:
            if self.require_config:
                raise ConfigurationError(
                    "real search provider is required for non-seed discovery sources",
                    {"provider": self.provider, "source_type": source.type.value},
                )
            return []

        query = query or self.build_query(product=product, campaign=campaign, source=source)
        if self.provider == "tavily":
            return self._search_tavily(query, source, limit)
        if self.provider == "brave":
            return self._search_brave(query, limit)
        return self._search_generic(query, product, campaign, source, limit)

    @staticmethod
    def build_query(
        *,
        product: ProductRead,
        campaign: CampaignRead,
        source: DiscoverySource,
    ) -> str:
        del product, campaign
        query = source.value.strip()
        if not query:
            raise ValueError("discovery source query is empty")
        return query

    def _search_generic(
        self,
        query: str,
        product: ProductRead,
        campaign: CampaignRead,
        source: DiscoverySource,
        limit: int,
    ) -> list[SearchResult]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            str(self.endpoint),
            headers=headers,
            timeout=self.timeout_seconds,
            json={
                "query": query,
                "source": source.model_dump(mode="json"),
                "product": product.model_dump(mode="json"),
                "campaign": campaign.model_dump(mode="json"),
                "limit": limit,
            },
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        return [SearchResult.model_validate(row) for row in rows[:limit]]

    def _lookup_generic(self, query: str, limit: int) -> list[SearchResult]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            str(self.endpoint),
            headers=headers,
            timeout=self.timeout_seconds,
            json={"query": query, "limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results", payload) if isinstance(payload, dict) else payload
        return [SearchResult.model_validate(row) for row in rows[:limit]]

    def _search_tavily(
        self, query: str, source: DiscoverySource, limit: int
    ) -> list[SearchResult]:
        response = httpx.post(
            str(self.endpoint or "https://api.tavily.com/search"),
            timeout=self.timeout_seconds,
            json={
                "api_key": self.api_key,
                "query": query,
                "max_results": limit,
                "search_depth": "basic",
            },
        )
        response.raise_for_status()
        rows = response.json().get("results", [])
        return [
            SearchResult(
                title=row.get("title") or row.get("url") or source.value,
                url=row.get("url"),
                snippet=row.get("content"),
                source="tavily",
                raw={**row, "query": query, "source_value": source.value},
            )
            for row in rows[:limit]
        ]

    def _search_brave(self, query: str, limit: int) -> list[SearchResult]:
        url = str(self.endpoint or "https://api.search.brave.com/res/v1/web/search")
        separator = "&" if "?" in url else "?"
        response = httpx.get(
            f"{url}{separator}{urlencode({'q': query, 'count': limit})}",
            timeout=self.timeout_seconds,
            headers={"X-Subscription-Token": self.api_key or "", "Accept": "application/json"},
        )
        response.raise_for_status()
        rows = response.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                title=row.get("title") or row.get("url") or query,
                url=row.get("url"),
                snippet=row.get("description"),
                source="brave",
                raw={**row, "query": query},
            )
            for row in rows[:limit]
        ]

    @staticmethod
    def _parse_seed(value: str, default_geography: str) -> SearchResult:
        try:
            parsed = json.loads(value)
            return SearchResult.model_validate(parsed)
        except Exception:
            parts = [part.strip() for part in value.split("|")]
            return SearchResult(
                title=parts[0],
                url=parts[1] if len(parts) > 1 else None,
                snippet=parts[2] if len(parts) > 2 else None,
                geography=parts[3] if len(parts) > 3 else default_geography,
                contact_email=parts[4] if len(parts) > 4 else None,
                source="seed",
                raw={"value": value},
            )

    @classmethod
    def _filter_business_results(
        cls,
        results: list[SearchResult],
        limit: int,
        product: ProductRead | None = None,
    ) -> list[SearchResult]:
        filtered = [result for result in results if cls._looks_like_business_result(result, product)]
        return filtered[:limit]

    @staticmethod
    def _looks_like_business_result(
        result: SearchResult,
        product: ProductRead | None = None,
    ) -> bool:
        if not result.url:
            return False
        parsed = urlparse(result.url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        title = result.title.lower()
        snippet = (result.snippet or "").lower()
        blocked_hosts = {
            "youtube.com",
            "youtu.be",
            "vimeo.com",
            "medium.com",
            "reddit.com",
            "quora.com",
            "wikipedia.org",
            "linkedin.com",
            "facebook.com",
            "instagram.com",
            "twitter.com",
            "x.com",
        }
        if host in blocked_hosts or any(host.endswith(f".{blocked}") for blocked in blocked_hosts):
            return False
        blocked_path_parts = (
            "/blog",
            "/blogs",
            "/article",
            "/articles",
            "/news",
            "/watch",
            "/video",
            "/videos",
            "/podcast",
            "/resources",
            "/learn",
            "/guide",
            "/guides",
            "/whitepaper",
        )
        if any(part in path for part in blocked_path_parts):
            return False
        blocked_title_phrases = (
            "best ",
            "top ",
            "how to ",
            "why ",
            "guide",
            "tips",
            "strategies",
            "blog",
            "article",
            "review",
            "reviews",
            "comparison",
            "alternatives",
            "software for",
            "apps for",
            "tools for",
            "near me",
            "watch",
            "video",
            "podcast",
            "template",
        )
        if any(phrase in title for phrase in blocked_title_phrases):
            return False
        if product and SearchTool._looks_like_solution_vendor_result(title, snippet, path, product):
            return False
        return True

    @staticmethod
    def _looks_like_solution_vendor_result(
        title: str,
        snippet: str,
        path: str,
        product: ProductRead,
    ) -> bool:
        target_customer = product.target_customer.lower()
        software_target_terms = (
            "software",
            "saas",
            "technology",
            "tech company",
            "developer",
            "engineering",
            "it team",
            "startup",
        )
        if any(term in target_customer for term in software_target_terms):
            return False

        text = " ".join([title, snippet, path.replace("-", " ").replace("_", " ")])
        vendor_pattern = re.compile(
            r"\b(software|app|apps|platform|tool|tools|saas|crm|cpq|automation|solution|solutions)\b",
            re.I,
        )
        solution_phrases = (
            "online approvals",
            "quote in ",
            "quotes in ",
            "estimate in ",
            "estimates in ",
            "in seconds",
            "in minutes",
        )
        return bool(vendor_pattern.search(text)) or any(phrase in text for phrase in solution_phrases)
