from __future__ import annotations

from campaign_sources.schemas import (
    CampaignSourceRead,
    CampaignSourceSlot,
    CampaignSourceMode,
)
from tools.discovery.google_places import GooglePlacesDiscoveryAdapter


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "places": [
                {
                    "id": "place_123",
                    "displayName": {"text": "Cedar & Sons Painting"},
                    "formattedAddress": "Austin, TX, USA",
                    "nationalPhoneNumber": "(512) 555-0101",
                    "websiteUri": "https://cedarpainting.example",
                    "googleMapsUri": "https://maps.google.com/?cid=123",
                    "businessStatus": "OPERATIONAL",
                    "rating": 4.8,
                    "userRatingCount": 42,
                    "types": ["painter", "home_goods_store"],
                }
            ]
        }


def test_google_places_adapter_maps_places_to_search_results(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, timeout, headers, json):
        calls.append({"url": url, "timeout": timeout, "headers": headers, "json": json})
        return FakeResponse()

    monkeypatch.setattr("tools.discovery.google_places.httpx.post", fake_post)

    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="google_places",
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": "residential painters", "geography": "Austin TX"},
        config={"limit": 5, "region_code": "US"},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )
    result = GooglePlacesDiscoveryAdapter(api_key="test-key").run(
        source,
        {
            "product": {
                "id": "product_1",
                "product_name": "Quote Tool",
                "product_description": "Quoting tool for painters.",
                "target_customer": "residential painters",
                "problem_being_solved": "quote follow-up is slow",
                "value_proposition": "send quotes faster",
                "target_geography": "United States",
                "validation_goal": "book interviews",
                "qualification_criteria": [{"label": "Residential painting business"}],
                "preferred_discovery_sources": [],
                "outreach_objective": "ask for interview",
                "constraints": [],
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
            "campaign": {
                "id": "campaign_1",
                "product_id": "product_1",
                "name": "Test campaign",
                "max_leads": 5,
                "channels": ["email"],
                "discovery_seeds": [],
                "status": "draft",
                "stage": "discovery",
                "goal_type": "learn",
                "icp_preset_id": "default",
                "source_preset_id": "default-web-validation",
                "source_input": None,
                "source_inputs": {},
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
        },
    )

    assert calls[0]["json"]["textQuery"] == "residential painters Austin TX"
    assert calls[0]["json"]["includePureServiceAreaBusinesses"] is True
    assert calls[0]["headers"]["X-Goog-Api-Key"] == "test-key"
    assert "places.displayName" in calls[0]["headers"]["X-Goog-FieldMask"]
    assert result.provider == "google_places"
    assert result.confidence == 90
    assert result.data[0]["title"] == "Cedar & Sons Painting"
    assert result.data[0]["url"] == "https://cedarpainting.example"
    assert result.data[0]["source"] == "google_places"
    assert "reviews: 42" in result.data[0]["snippet"]


def test_google_places_adapter_does_not_append_broad_geography(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, timeout, headers, json):
        calls.append(json)
        return FakeResponse()

    monkeypatch.setattr("tools.discovery.google_places.httpx.post", fake_post)

    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="google_places",
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": "residential painters Austin TX", "geography": "United States, Canada"},
        config={"limit": 5, "region_code": "US"},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )
    GooglePlacesDiscoveryAdapter(api_key="test-key").run(
        source,
        {
            "product": {
                "id": "product_1",
                "product_name": "Quote Tool",
                "product_description": "Quoting tool for painters.",
                "target_customer": "residential painters",
                "problem_being_solved": "quote follow-up is slow",
                "value_proposition": "send quotes faster",
                "target_geography": "United States, Canada",
                "validation_goal": "book interviews",
                "qualification_criteria": [{"label": "Residential painting business"}],
                "preferred_discovery_sources": [],
                "outreach_objective": "ask for interview",
                "constraints": [],
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
            "campaign": {
                "id": "campaign_1",
                "product_id": "product_1",
                "name": "Test campaign",
                "max_leads": 5,
                "channels": ["email"],
                "discovery_seeds": [],
                "status": "draft",
                "stage": "discovery",
                "goal_type": "learn",
                "icp_preset_id": "default",
                "source_preset_id": "google-places-local-business",
                "source_input": None,
                "source_inputs": {},
                "created_at": "2026-08-20T00:00:00Z",
                "updated_at": "2026-08-20T00:00:00Z",
            },
        },
    )

    assert calls[0]["textQuery"] == "residential painters Austin TX"
