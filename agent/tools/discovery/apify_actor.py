from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

import httpx

from campaign_sources.schemas import CampaignSourceRead
from campaigns.schemas import CampaignRead
from shared.errors import ConfigurationError
from shared.utils import truncate
from tools.base import ToolResult, ToolSlot, measured_tool_result
from tools.search import SearchResult


DEFAULT_APIFY_API_BASE_URL = "https://api.apify.com/v2"
DEFAULT_RESULT_MAPPING = {
    "title": ["title", "name", "listingTitle", "adTitle", "headline"],
    "url": ["url", "listingUrl", "adUrl", "link", "canonicalUrl"],
    "snippet": ["description", "details", "summary", "body", "snippet", "shortDescription"],
    "geography": ["location", "address", "city"],
    "contact_email": ["email", "contactEmail", "sellerEmail"],
}


class ApifyActorDiscoveryAdapter:
    def __init__(
        self,
        *,
        provider_id: str,
        api_token: str | None,
        actor_id: str | None,
        api_base_url: str | None = None,
        input_template: str | dict[str, Any] | None = None,
        result_mapping: str | dict[str, Any] | None = None,
        max_charge_usd: float | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.provider_id = provider_id
        self.api_token = api_token
        self.actor_id = actor_id
        self.api_base_url = (api_base_url or DEFAULT_APIFY_API_BASE_URL).rstrip("/")
        self.input_template = input_template
        self.result_mapping = result_mapping
        self.max_charge_usd = max_charge_usd
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.provider_id and self.api_token and self.actor_id)

    def run(self, source: CampaignSourceRead, context: dict[str, Any]) -> ToolResult:
        if not self.is_configured:
            raise ConfigurationError(
                "Apify actor source is missing api_token, actor_id, or provider id",
                {"campaign_source_id": source.id, "provider_id": source.provider_id},
            )

        campaign = CampaignRead.model_validate(context["campaign"])
        query = str(source.input.get("query") or "").strip()
        if not query:
            raise ConfigurationError(
                "Apify actor source query is empty",
                {"campaign_source_id": source.id, "provider_id": source.provider_id},
            )

        limit = int(source.config.get("limit") or campaign.max_leads)
        actor_id = _normalize_actor_id(str(source.config.get("actor_id") or self.actor_id or ""))
        actor_input = self._actor_input(source=source, query=query, limit=limit)
        mapping = self._result_mapping(source)
        params: dict[str, Any] = {
            "token": self.api_token,
            "format": "json",
            "clean": "true",
            "limit": limit,
            "maxItems": limit,
        }
        max_charge = source.budget_limit if source.budget_limit is not None else self.max_charge_usd
        if max_charge is not None:
            params["maxTotalChargeUsd"] = max_charge

        endpoint = f"{self.api_base_url}/actors/{quote(actor_id, safe='~')}/run-sync-get-dataset-items"

        def action() -> list[dict[str, Any]]:
            try:
                response = httpx.post(
                    endpoint,
                    params=params,
                    timeout=max(self.timeout_seconds, 60.0),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    json=actor_input,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ConfigurationError(
                    "Apify actor request failed",
                    {
                        "provider_id": self.provider_id,
                        "actor_id": actor_id,
                        "status_code": exc.response.status_code,
                        "response_body": truncate(exc.response.text, 1000),
                    },
                ) from exc
            except httpx.TimeoutException as exc:
                raise ConfigurationError(
                    "Apify actor request timed out",
                    {
                        "provider_id": self.provider_id,
                        "actor_id": actor_id,
                        "timeout_seconds": max(self.timeout_seconds, 60.0),
                    },
                ) from exc
            except httpx.RequestError as exc:
                raise ConfigurationError(
                    "Apify actor request could not be completed",
                    {
                        "provider_id": self.provider_id,
                        "actor_id": actor_id,
                        "error": exc.__class__.__name__,
                    },
                ) from exc
            rows = response.json()
            if isinstance(rows, dict):
                rows = rows.get("items", rows.get("results", []))
            if not isinstance(rows, list):
                rows = []
            return [
                self._to_search_result(
                    row=row,
                    query=query,
                    mapping=mapping,
                    provider_id=self.provider_id,
                ).model_dump(mode="json")
                for row in rows[:limit]
            ]

        return measured_tool_result(
            provider=self.provider_id,
            slot=ToolSlot.DISCOVERY,
            confidence=80,
            source_urls=[],
            raw={
                "campaign_source_id": source.id,
                "provider_id": source.provider_id,
                "input": source.input,
                "config": source.config,
                "apify_actor_id": actor_id,
                "request": actor_input,
                "params": {key: value for key, value in params.items() if key != "token"},
            },
            action=action,
        )

    def _actor_input(
        self,
        *,
        source: CampaignSourceRead,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        values = {
            "query": query,
            "limit": limit,
            "max_results": limit,
            "source_url": query if _is_url(query) else "",
        }
        configured_input = source.config.get("actor_input")
        if isinstance(configured_input, dict):
            return _render_template(configured_input, values)
        if self.input_template:
            parsed = _json_object(self.input_template, "APIFY_ACTOR_INPUT_TEMPLATE")
            return _render_template(parsed, values)
        raise ConfigurationError(
            "Apify actor input template is missing",
            {
                "provider_id": self.provider_id,
                "campaign_source_id": source.id,
                "required_config": (
                    "Set actor_input on the campaign source or input_template on the "
                    "Apify source configuration."
                ),
            },
        )

    def _result_mapping(self, source: CampaignSourceRead) -> dict[str, list[str]]:
        configured_mapping = source.config.get("result_mapping")
        if isinstance(configured_mapping, dict):
            return _normalize_mapping(configured_mapping)
        if self.result_mapping:
            return _normalize_mapping(_json_object(self.result_mapping, "APIFY_ACTOR_RESULT_MAPPING"))
        return DEFAULT_RESULT_MAPPING

    @staticmethod
    def _to_search_result(
        *,
        row: dict[str, Any],
        query: str,
        mapping: dict[str, list[str]],
        provider_id: str,
    ) -> SearchResult:
        title = _first_text(row, mapping.get("title", [])) or query
        url = _first_text(row, mapping.get("url", []))
        snippet = _first_text(row, mapping.get("snippet", []))
        geography = _first_text(row, mapping.get("geography", []))
        contact_email = _first_text(row, mapping.get("contact_email", []))
        return SearchResult(
            title=title,
            url=url,
            snippet=snippet,
            geography=geography,
            contact_email=contact_email,
            source=provider_id,
            raw={**row, "query": query},
        )


def _normalize_actor_id(value: str) -> str:
    return value.strip().replace("/", "~")


def _is_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _json_object(value: str | dict[str, Any], name: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{name} must be valid JSON", {"error": str(exc)}) from exc
    if not isinstance(parsed, dict):
        raise ConfigurationError(f"{name} must be a JSON object", {"template_type": type(parsed).__name__})
    return parsed


def _render_template(value: Any, values: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render_template(child, values) for key, child in value.items()}
    if isinstance(value, list):
        return [_render_template(child, values) for child in value]
    if isinstance(value, str):
        match = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", value)
        if match:
            return values.get(match.group(1), "")
        rendered = value
        for key, replacement in values.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(replacement))
            rendered = rendered.replace(f"{{{{ {key} }}}}", str(replacement))
        return rendered
    return value


def _normalize_mapping(mapping: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for output_field, keys in mapping.items():
        if isinstance(keys, str):
            normalized[str(output_field)] = [keys]
        elif isinstance(keys, list):
            normalized[str(output_field)] = [str(key) for key in keys]
    return {**DEFAULT_RESULT_MAPPING, **normalized}


def _first_text(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = _deep_get(row, key)
        if value is None:
            continue
        if isinstance(value, dict):
            value = value.get("text") or value.get("name") or value.get("value")
        if isinstance(value, (int, float)):
            value = str(value)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _deep_get(row: dict[str, Any], key: str) -> Any:
    value: Any = row
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value
