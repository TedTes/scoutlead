from seeding.openstreetmap import (
    NICHE_PLANS,
    OpenStreetMapSeedCollector,
    build_overpass_query,
    seed_from_osm_element,
)


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "elements": [
                {
                    "type": "node",
                    "id": 123,
                    "lat": 43.7,
                    "lon": -79.4,
                    "tags": {
                        "name": "Apex Roofing",
                        "craft": "roofer",
                        "website": "https://apex-roofing.example",
                        "phone": "+1-416-555-0101",
                        "addr:city": "Toronto",
                        "addr:province": "ON",
                    },
                }
            ]
        }


def test_overpass_collector_creates_auditable_niche_seed(monkeypatch) -> None:
    calls = []

    def fake_post(url, *, data, headers, timeout):
        calls.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("seeding.openstreetmap.httpx.post", fake_post)
    result = OpenStreetMapSeedCollector(endpoint="https://overpass.example").collect(
        NICHE_PLANS["home_service_roofing"],
        seed_market="Toronto/GTA",
        target_count=10,
    )

    assert result.elements_read == 1
    assert len(result.rows) == 1
    assert result.rows[0].company_name == "Apex Roofing"
    assert result.rows[0].seed_niche == "home_service_roofing"
    assert result.rows[0].source_url == "https://www.openstreetmap.org/node/123"
    assert result.rows[0].raw["license"] == "ODbL"
    assert "out center tags;" in calls[0]["data"]["data"]


def test_cleaning_plan_excludes_dry_cleaners() -> None:
    seed = seed_from_osm_element(
        {
            "type": "node",
            "id": 44,
            "tags": {"name": "Example Dry Cleaning", "craft": "cleaner"},
        },
        plan=NICHE_PLANS["home_service_cleaning"],
        seed_market="Toronto/GTA",
    )

    assert seed is None


def test_overpass_query_contains_niche_tag_and_name_filters() -> None:
    query = build_overpass_query(
        NICHE_PLANS["home_service_hvac"],
        bbox=(43.4, -79.95, 44.15, -78.85),
    )

    assert '["craft"="hvac"]' in query
    assert '["name"~"hvac|heating|cooling|air conditioning",i]' in query
