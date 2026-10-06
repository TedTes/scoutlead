from __future__ import annotations

import json

from seeding.google_places import (
    GooglePlacesSeedCollector,
    GooglePlacesSeedQuery,
    build_home_service_painting_queries,
    build_niche_queries,
    seed_dedupe_key,
    seed_from_place,
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


def test_google_places_seed_dedupes_distinct_place_ids_by_phone(monkeypatch) -> None:
    def fake_post(url, *, timeout, headers, json):
        del url, timeout, headers, json
        return FakePlacesResponse(
            {
                "places": [
                    {
                        "id": "branch_1",
                        "displayName": {"text": "Home Painters Toronto"},
                        "formattedAddress": "Toronto, ON",
                        "nationalPhoneNumber": "416-555-0101",
                        "businessStatus": "OPERATIONAL",
                    },
                    {
                        "id": "branch_2",
                        "displayName": {"text": "Home Painters Toronto"},
                        "formattedAddress": "North York, ON",
                        "nationalPhoneNumber": "416-555-0101",
                        "businessStatus": "OPERATIONAL",
                    },
                ]
            }
        )

    monkeypatch.setattr("seeding.google_places.httpx.post", fake_post)
    result = GooglePlacesSeedCollector(api_key="test-key").collect(
        [GooglePlacesSeedQuery(text_query="painters Toronto", seed_market="Toronto")],
        target_count=10,
    )

    assert [row.external_id for row in result.rows] == ["branch_1"]


def test_home_service_painting_query_plan_can_cover_large_seed() -> None:
    queries = build_home_service_painting_queries()

    assert len(queries) > 100
    assert queries[0].text_query == "residential painters Toronto ON"
    assert queries[0].region_code == "CA"


def test_query_plan_keeps_each_niche_taxonomy() -> None:
    queries = build_niche_queries(
        seed_niche="home_service_roofing",
        cities=["Toronto ON"],
    )

    assert queries[0].text_query == "roofing contractors Toronto ON"
    assert queries[0].seed_niche == "home_service_roofing"
    assert queries[0].included_type == "roofing_contractor"

    hvac_queries = build_niche_queries(
        seed_niche="home_service_hvac",
        cities=["Toronto ON"],
    )
    assert hvac_queries[0].included_type is None


def test_query_plan_keeps_canonical_city_separate_from_search_locality() -> None:
    queries = build_niche_queries(
        seed_niche="home_service_painting",
        cities=["North York ON"],
        city="Toronto",
    )

    assert queries[0].text_query == "residential painters North York ON"
    assert queries[0].city == "Toronto"


def test_google_places_seed_enforces_radius_and_sets_structured_attributes() -> None:
    query = GooglePlacesSeedQuery(
        text_query="CertaPro Painters Toronto",
        seed_market="Toronto",
        seed_niche="home_service_painting",
        city="Toronto",
        center_latitude=43.6532,
        center_longitude=-79.3832,
        radius_meters=25_000,
        customer_kind="residential",
        require_phone=True,
    )
    inside = {
        "id": "inside",
        "displayName": {"text": "CertaPro Painters of Toronto"},
        "formattedAddress": "Toronto, ON, Canada",
        "nationalPhoneNumber": "(416) 555-0199",
        "businessStatus": "OPERATIONAL",
        "location": {"latitude": 43.66, "longitude": -79.39},
        "types": ["painter"],
    }
    outside = {
        **inside,
        "id": "outside",
        "displayName": {"text": "Remote Painter"},
        "location": {"latitude": 44.1, "longitude": -79.39},
    }

    seed = seed_from_place(inside, query=query)

    assert seed is not None
    assert seed.city == "Toronto"
    assert seed.latitude == 43.66
    assert seed.longitude == -79.39
    assert seed.customer_kind == "residential"
    assert seed.is_chain is True
    assert seed.is_franchise is True
    assert seed.raw["website_presence"]["status"] == "no_website_listed"
    assert seed_from_place(outside, query=query) is None


def test_google_places_seed_marks_known_chain_without_assuming_franchise() -> None:
    query = GooglePlacesSeedQuery(
        text_query="HVAC Toronto",
        seed_market="Toronto",
        seed_niche="home_service_hvac",
    )
    place = {
        "id": "reliance",
        "displayName": {"text": "Reliance Home Comfort"},
        "businessStatus": "OPERATIONAL",
    }

    seed = seed_from_place(place, query=query)

    assert seed is not None
    assert seed.is_chain is True
    assert seed.is_franchise is None


def test_google_places_hvac_seed_rejects_generic_query_result() -> None:
    query = GooglePlacesSeedQuery(
        text_query="HVAC contractors Toronto",
        seed_market="Toronto",
        seed_niche="home_service_hvac",
    )
    generic = {
        "id": "generic",
        "displayName": {"text": "Hudson Condominium Solutions Inc"},
        "businessStatus": "OPERATIONAL",
    }
    hvac = {
        "id": "hvac",
        "displayName": {"text": "Hudson Heating and Cooling Inc"},
        "businessStatus": "OPERATIONAL",
    }

    assert seed_from_place(generic, query=query) is None
    assert seed_from_place(hvac, query=query) is not None


def test_named_google_places_seed_rejects_a_different_business() -> None:
    query = GooglePlacesSeedQuery(
        text_query="Royal Home Painters",
        expected_name="Royal Home Painters",
        seed_market="Toronto",
    )
    unrelated = {
        "id": "unrelated",
        "displayName": {"text": "Downtown Painting Services"},
        "businessStatus": "OPERATIONAL",
    }
    variant = {
        "id": "variant",
        "displayName": {"text": "Royal Home Painters Toronto"},
        "businessStatus": "OPERATIONAL",
    }

    assert seed_from_place(unrelated, query=query) is None
    assert seed_from_place(variant, query=query) is not None

    missing_distinctive_name = {
        "id": "missing-distinctive-name",
        "displayName": {"text": "Home Painters Toronto"},
        "businessStatus": "OPERATIONAL",
    }
    amazon_query = GooglePlacesSeedQuery(
        text_query="Amazonia Home Painters Toronto",
        expected_name="Amazonia Home Painters Toronto",
        seed_market="Toronto",
    )
    assert seed_from_place(missing_distinctive_name, query=amazon_query) is None

    picture_query = GooglePlacesSeedQuery(
        text_query="Picture Perfect Painters",
        expected_name="Picture Perfect Painters",
        seed_market="Toronto",
    )
    perfect_painter = {
        "id": "perfect-painter",
        "displayName": {"text": "Perfect Painter"},
        "businessStatus": "OPERATIONAL",
    }
    assert seed_from_place(perfect_painter, query=picture_query) is None


def test_google_places_exact_queries_can_limit_each_query_to_one_result(monkeypatch) -> None:
    def fake_post(url, *, timeout, headers, json):
        del url, timeout, headers, json
        return FakePlacesResponse(
            {
                "places": [
                    {
                        "id": "first",
                        "displayName": {"text": "Exact Painter"},
                        "businessStatus": "OPERATIONAL",
                    },
                    {
                        "id": "second",
                        "displayName": {"text": "Loose Result"},
                        "businessStatus": "OPERATIONAL",
                    },
                ]
            }
        )

    monkeypatch.setattr("seeding.google_places.httpx.post", fake_post)
    result = GooglePlacesSeedCollector(api_key="test-key").collect(
        [GooglePlacesSeedQuery(text_query="Exact Painter", seed_market="Toronto")],
        target_count=10,
        max_results_per_query=1,
    )

    assert [row.company_name for row in result.rows] == ["Exact Painter"]


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
