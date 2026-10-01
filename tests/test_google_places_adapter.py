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


def test_google_places_adapter_paginates_up_to_source_limit(monkeypatch) -> None:
    calls = []

    class PageResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    def place(index: int) -> dict:
        return {
            "id": f"place_{index}",
            "displayName": {"text": f"Business {index}"},
            "formattedAddress": "Toronto, ON",
        }

    def fake_post(url, *, timeout, headers, json):
        calls.append(json)
        if len(calls) == 1:
            return PageResponse({"places": [place(index) for index in range(20)], "nextPageToken": "page-2"})
        return PageResponse({"places": [place(index) for index in range(20, 25)]})

    monkeypatch.setattr("tools.discovery.google_places.httpx.post", fake_post)
    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="google_places",
        mode=CampaignSourceMode.ACCUMULATE,
        input={"query": "painters", "geography": "Toronto"},
        config={"limit": 25, "region_code": "CA"},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )

    result = GooglePlacesDiscoveryAdapter(api_key="test-key").run(
        source,
        {
            "product": _product_context(),
            "campaign": _campaign_context(max_leads=25),
        },
    )

    assert len(result.data) == 25
    assert calls[0]["pageSize"] == 20
    assert calls[1]["pageSize"] == 5
    assert calls[1]["pageToken"] == "page-2"


def test_google_places_adapter_keeps_reachable_active_businesses_without_websites(
    monkeypatch,
) -> None:
    calls = []

    class NeighborhoodResponse:
        def __init__(self, query: str):
            self.query = query

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            suffix = "scarborough" if "Scarborough" in self.query else "etobicoke"
            return {
                "places": [
                    {
                        "id": f"no-site-{suffix}",
                        "displayName": {"text": f"Independent Painter {suffix}"},
                        "formattedAddress": f"1 Main St, {suffix}, ON",
                        "nationalPhoneNumber": "(416) 555-0101",
                        "googleMapsUri": f"https://maps.google.com/?cid={suffix}",
                        "businessStatus": "OPERATIONAL",
                    },
                    {
                        "id": f"has-site-{suffix}",
                        "displayName": {"text": "Painter With Website"},
                        "websiteUri": "https://painter.example",
                        "nationalPhoneNumber": "(416) 555-0102",
                        "businessStatus": "OPERATIONAL",
                    },
                    {
                        "id": f"closed-{suffix}",
                        "displayName": {"text": "Closed Painter"},
                        "nationalPhoneNumber": "(416) 555-0103",
                        "businessStatus": "CLOSED_PERMANENTLY",
                    },
                ]
            }

    def fake_post(url, *, timeout, headers, json):
        calls.append(json)
        return NeighborhoodResponse(json["textQuery"])

    monkeypatch.setattr("tools.discovery.google_places.httpx.post", fake_post)
    source = CampaignSourceRead(
        id="campaign_source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="google_places",
        mode=CampaignSourceMode.ACCUMULATE,
        input={
            "query": "painters Toronto ON",
            "search_queries": [
                "painters in Scarborough ON",
                "painters in Etobicoke ON",
            ],
            "website_policy": "missing",
        },
        config={"limit": 4, "region_code": "CA"},
        priority=10,
        enabled=True,
        created_at="2026-08-20T00:00:00Z",
        updated_at="2026-08-20T00:00:00Z",
    )

    result = GooglePlacesDiscoveryAdapter(api_key="test-key").run(
        source,
        {
            "product": _product_context(),
            "campaign": _campaign_context(max_leads=4),
        },
    )

    assert [call["textQuery"] for call in calls] == [
        "painters in Scarborough ON",
        "painters in Etobicoke ON",
    ]
    assert all(call["pageSize"] == 2 for call in calls)
    assert len(result.data) == 2
    assert all(row["url"] is None for row in result.data)
    assert all(row["raw"]["businessStatus"] == "OPERATIONAL" for row in result.data)
    assert all(
        row["raw"]["website_presence_label"] == "No website listed"
        for row in result.data
    )


def test_missing_or_unavailable_policy_keeps_sites_for_availability_audit() -> None:
    place = {
        "businessStatus": "OPERATIONAL",
        "websiteUri": "https://painter.example",
        "nationalPhoneNumber": "(416) 555-0101",
    }

    assert GooglePlacesDiscoveryAdapter._matches_website_policy(place, "missing") is False
    assert (
        GooglePlacesDiscoveryAdapter._matches_website_policy(
            place,
            "missing_or_unavailable",
        )
        is True
    )


def test_google_places_deduplicates_distinct_place_ids_with_same_name_and_phone() -> None:
    first = {
        "id": "place-1",
        "displayName": {"text": "Neighborhood Painting Ltd."},
        "formattedAddress": "1 Main St, Toronto, ON",
        "nationalPhoneNumber": "(416) 555-0101",
    }
    second = {
        "id": "place-2",
        "displayName": {"text": "Neighborhood Painting"},
        "formattedAddress": "Toronto, ON",
        "nationalPhoneNumber": "416-555-0101",
    }

    assert (
        GooglePlacesDiscoveryAdapter._place_keys(first)
        & GooglePlacesDiscoveryAdapter._place_keys(second)
    )


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


def _product_context() -> dict:
    return {
        "id": "product_1",
        "product_name": "Website Growth",
        "product_description": "Website improvements for local businesses.",
        "target_customer": "residential painters",
        "problem_being_solved": "weak websites",
        "value_proposition": "generate more inquiries",
        "target_geography": "Toronto",
        "validation_goal": "find opportunities",
        "qualification_criteria": [{"label": "Residential painting business"}],
        "preferred_discovery_sources": [],
        "outreach_objective": "contact qualified businesses",
        "constraints": [],
        "created_at": "2026-08-20T00:00:00Z",
        "updated_at": "2026-08-20T00:00:00Z",
    }


def _campaign_context(*, max_leads: int) -> dict:
    return {
        "id": "campaign_1",
        "product_id": "product_1",
        "name": "Test campaign",
        "max_leads": max_leads,
        "channels": ["manual"],
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
    }
