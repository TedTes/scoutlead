from __future__ import annotations

import json

from seeding.google_places import (
    GooglePlacesSeedCollector,
    GooglePlacesSeedQuery,
    build_home_service_painting_queries,
    seed_dedupe_key,
)
from scripts.collect_google_places_seed import read_existing_seeds, write_jsonl


class FakePlacesResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_google_places_seed_collector_paginates_and_dedupes(monkeypatch) -> None:
    calls = []
    responses = [
        FakePlacesResponse(
            {
                "places": [
                    {
                        "id": "place_1",
                        "displayName": {"text": "Apex Painting"},
                        "formattedAddress": "Toronto, ON, Canada",
                        "nationalPhoneNumber": "(416) 555-0101",
                        "websiteUri": "https://apex.example",
                        "googleMapsUri": "https://maps.example/apex",
                        "businessStatus": "OPERATIONAL",
                        "rating": 4.8,
                        "userRatingCount": 40,
                        "types": ["painter"],
                    },
                    {
                        "id": "place_1",
                        "displayName": {"text": "Apex Painting Duplicate"},
                        "formattedAddress": "Toronto, ON, Canada",
                    },
                ],
                "nextPageToken": "next-token",
            }
        ),
        FakePlacesResponse(
            {
                "places": [
                    {
                        "id": "place_2",
                        "displayName": {"text": "Birch House Painters"},
                        "formattedAddress": "North York, ON, Canada",
                        "nationalPhoneNumber": "(416) 555-0102",
                        "businessStatus": "OPERATIONAL",
                        "types": ["painter"],
                    }
                ]
            }
        ),
    ]

    def fake_post(url, *, timeout, headers, json):
        del timeout
        calls.append({"url": url, "headers": headers, "json": json})
        return responses.pop(0)

    monkeypatch.setattr("seeding.google_places.httpx.post", fake_post)

    collector = GooglePlacesSeedCollector(
        api_key="test-key",
        endpoint="https://places.example/searchText",
        page_delay_seconds=0,
    )
    result = collector.collect(
        [
            GooglePlacesSeedQuery(
                text_query="residential painters Toronto ON",
                seed_market="Toronto/GTA",
            )
        ],
        target_count=10,
        max_requests=5,
    )

    assert result.requests_made == 2
    assert result.queries_attempted == 1
    assert len(result.rows) == 2
    assert [row.company_name for row in result.rows] == ["Apex Painting", "Birch House Painters"]
    assert result.rows[0].source == "google_places_seed"
    assert result.rows[0].external_id == "place_1"
    assert result.rows[0].phone == "(416) 555-0101"
    assert "public website" in result.rows[0].signals
    assert calls[0]["json"]["pageSize"] == 20
    assert calls[0]["json"]["includedType"] == "painter"
    assert calls[1]["json"]["pageToken"] == "next-token"
    assert "nextPageToken" in calls[0]["headers"]["X-Goog-FieldMask"]


def test_google_places_seed_collector_honors_existing_rows(monkeypatch) -> None:
    existing = GooglePlacesSeedQuery(
        text_query="house painters Toronto ON",
        seed_market="Toronto/GTA",
    )
    existing_row = {
        "id": "place_1",
        "displayName": {"text": "Apex Painting"},
        "formattedAddress": "Toronto, ON, Canada",
        "nationalPhoneNumber": "(416) 555-0101",
        "businessStatus": "OPERATIONAL",
        "types": ["painter"],
    }
    from seeding.google_places import seed_from_place

    seed = seed_from_place(existing_row, query=existing)
    assert seed is not None

    def fake_post(url, *, timeout, headers, json):
        del url, timeout, headers, json
        return FakePlacesResponse(
            {
                "places": [
                    existing_row,
                    {
                        "id": "place_2",
                        "displayName": {"text": "Birch House Painters"},
                        "formattedAddress": "North York, ON, Canada",
                        "businessStatus": "OPERATIONAL",
                        "types": ["painter"],
                    },
                ]
            }
        )

    monkeypatch.setattr("seeding.google_places.httpx.post", fake_post)

    result = GooglePlacesSeedCollector(api_key="test-key", page_delay_seconds=0).collect(
        [existing],
        target_count=10,
        existing=[seed],
    )

    assert [row.external_id for row in result.rows] == ["place_1", "place_2"]


def test_home_service_painting_query_plan_can_cover_large_seed() -> None:
    queries = build_home_service_painting_queries()

    assert len(queries) > 100
    assert queries[0].text_query == "residential painters Toronto ON"
    assert queries[0].region_code == "CA"


def test_seed_jsonl_round_trips_with_dedupe(tmp_path) -> None:
    rows = [
        {
            "company_name": "Apex Painting",
            "external_id": "place_1",
            "source": "google_places_seed",
        },
        {
            "company_name": "Apex Painting duplicate",
            "external_id": "place_1",
            "source": "google_places_seed",
        },
    ]
    path = tmp_path / "seed.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    seeds = read_existing_seeds(path)
    rewritten = tmp_path / "rewritten.jsonl"
    write_jsonl(rewritten, seeds)

    assert len(seeds) == 1
    assert seed_dedupe_key(seeds[0]) == "external:google_places_seed:place_1"
    assert len(rewritten.read_text(encoding="utf-8").splitlines()) == 1
