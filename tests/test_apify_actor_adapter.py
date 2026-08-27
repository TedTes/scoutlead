from __future__ import annotations

import httpx
import pytest

from campaign_sources.schemas import CampaignSourceMode, CampaignSourceRead, CampaignSourceSlot
from shared.errors import ConfigurationError
from tools.discovery.apify_actor import ApifyActorDiscoveryAdapter
from tools.search import SearchTool
from tools.source_registry import SourceAdapterRegistry


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return [
            {
                "title": "Cedar Painting",
                "listingUrl": "https://example.test/listing/1",
                "description": "Residential painting service",
                "location": "Toronto, ON",
                "email": "owner@example.test",
            }
        ]


def test_apify_actor_adapter_uses_configured_provider_and_template(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, params, timeout, headers, json):
        calls.append(
            {
                "url": url,
                "params": params,
                "timeout": timeout,
                "headers": headers,
                "json": json,
            }
        )
        return FakeResponse()

    monkeypatch.setattr("tools.discovery.apify_actor.httpx.post", fake_post)

    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="classifieds",
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": "painting service Toronto ON"},
        config={"limit": 5},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )
    adapter = ApifyActorDiscoveryAdapter(
        provider_id="classifieds",
        api_token="secret-token",
        actor_id="owner/source-actor",
        input_template='{"searchQueries":["{{query}}"],"maxResults":"{{limit}}"}',
        result_mapping='{"url":["listingUrl"],"contact_email":["email"]}',
    )

    result = adapter.run(
        source,
        {
            "product": {
                "id": "product_1",
                "product_name": "Quote Tool",
                "product_description": "Quoting tool for painters.",
                "target_customer": "residential painters",
                "problem_being_solved": "quote follow-up is slow",
                "value_proposition": "send quotes faster",
                "target_geography": "Canada",
                "validation_goal": "list contacts",
                "qualification_criteria": [{"label": "Residential painting business"}],
                "preferred_discovery_sources": [],
                "outreach_objective": "none",
                "constraints": [],
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
            "campaign": {
                "id": "campaign_1",
                "product_id": "product_1",
                "name": "Source request",
                "max_leads": 5,
                "channels": ["manual"],
                "discovery_seeds": [],
                "status": "draft",
                "stage": "discovery",
                "goal_type": "learn",
                "icp_preset_id": "default",
                "source_preset_id": "apify-actor-source",
                "source_input": None,
                "source_inputs": {},
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
        },
    )

    assert calls[0]["url"].endswith("/actors/owner~source-actor/run-sync-get-dataset-items")
    assert calls[0]["params"]["token"] == "secret-token"
    assert calls[0]["params"]["maxItems"] == 5
    assert calls[0]["json"] == {
        "searchQueries": ["painting service Toronto ON"],
        "maxResults": 5,
    }
    assert "token" not in result.raw["params"]
    assert result.provider == "classifieds"
    assert result.data[0]["source"] == "classifieds"
    assert result.data[0]["title"] == "Cedar Painting"
    assert result.data[0]["url"] == "https://example.test/listing/1"
    assert result.data[0]["contact_email"] == "owner@example.test"


def test_source_registry_registers_multiple_apify_sources() -> None:
    registry = SourceAdapterRegistry(
        search_tool=SearchTool(),
        apify_api_token="global-token",
        apify_sources=[
            {"id": "kijiji", "actor_id": "owner/kijiji"},
            {"id": "homestars", "actor_id": None},
        ],
    )

    assert "kijiji" in registry.adapters
    assert "homestars" in registry.adapters
    assert registry.missing_configuration(["kijiji", "homestars"]) == ["homestars"]


def test_apify_actor_adapter_wraps_provider_http_errors(monkeypatch) -> None:
    def fake_post(url, *, params, timeout, headers, json):
        del params, timeout, headers, json
        request = httpx.Request("POST", url)
        response = httpx.Response(
            404,
            request=request,
            text='{"error":"Actor was not found"}',
        )
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr("tools.discovery.apify_actor.httpx.post", fake_post)

    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="kijiji",
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": "painting service Toronto ON"},
        config={"limit": 5, "actor_input": {"query": "{{query}}", "maxResults": "{{limit}}"}},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )
    adapter = ApifyActorDiscoveryAdapter(
        provider_id="kijiji",
        api_token="secret-token",
        actor_id="owner/missing-actor",
    )

    with pytest.raises(ConfigurationError) as exc_info:
        adapter.run(
            source,
            {
                "campaign": {
                    "id": "campaign_1",
                    "product_id": "product_1",
                    "name": "Source request",
                    "max_leads": 5,
                    "channels": ["manual"],
                    "discovery_seeds": [],
                    "status": "draft",
                    "stage": "discovery",
                    "goal_type": "learn",
                    "icp_preset_id": "default",
                    "source_preset_id": "apify-actor-source",
                    "source_input": None,
                    "source_inputs": {},
                    "created_at": "2026-08-20T00:00:00Z",
                    "updated_at": "2026-08-20T00:00:00Z",
                },
            },
        )

    assert exc_info.value.message == "Apify actor request failed"
    assert exc_info.value.details["provider_id"] == "kijiji"
    assert exc_info.value.details["actor_id"] == "owner~missing-actor"
    assert exc_info.value.details["status_code"] == 404
    assert "Actor was not found" in exc_info.value.details["response_body"]
    assert "secret-token" not in str(exc_info.value.details)
