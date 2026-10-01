from campaign_sources.schemas import CampaignSourceMode, CampaignSourceRead, CampaignSourceSlot
from tools.discovery.openstreetmap import OpenStreetMapDiscoveryAdapter, build_overpass_query


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_openstreetmap_adapter_geocodes_fetches_and_normalizes(monkeypatch) -> None:
    monkeypatch.setattr(
        "tools.discovery.openstreetmap.httpx.get",
        lambda *args, **kwargs: FakeResponse(
            [{"boundingbox": ["43.55", "43.90", "-79.70", "-79.10"]}]
        ),
    )
    monkeypatch.setattr(
        "tools.discovery.openstreetmap.httpx.post",
        lambda *args, **kwargs: FakeResponse(
            {
                "elements": [
                    {
                        "type": "node",
                        "id": 42,
                        "tags": {
                            "name": "Neighbourhood Painting",
                            "craft": "painter",
                            "phone": "+1 416 555 0101",
                            "addr:city": "Toronto",
                        },
                    }
                ]
            }
        ),
    )
    result = OpenStreetMapDiscoveryAdapter(timeout_seconds=1).run(
        _source(),
        {"campaign": _campaign()},
    )

    assert result.provider == "openstreetmap"
    assert result.data[0]["title"] == "Neighbourhood Painting"
    assert result.data[0]["url"] is None
    assert result.data[0]["raw"]["external_id"] == "osm:node:42"
    assert result.data[0]["raw"]["website_presence_status"] == "no_website_listed"


def test_openstreetmap_query_uses_category_tag_and_name_pattern() -> None:
    query = build_overpass_query("residential painters", bbox=(43.5, -79.7, 43.9, -79.1))

    assert '["craft"="painter"]' in query
    assert 'paint|painter|painting' in query


def _source() -> CampaignSourceRead:
    return CampaignSourceRead(
        id="source_1",
        campaign_id="campaign_1",
        slot=CampaignSourceSlot.DISCOVERY,
        provider_id="openstreetmap",
        mode=CampaignSourceMode.ACCUMULATE,
        input={
            "query": "residential painters Toronto",
            "business_category": "residential painters",
            "location": "Toronto",
        },
        config={"limit": 10, "website_policy": "missing"},
        priority=20,
        enabled=True,
        created_at="2026-10-01T00:00:00Z",
        updated_at="2026-10-01T00:00:00Z",
    )


def _campaign() -> dict:
    return {
        "id": "campaign_1",
        "product_id": "product_1",
        "name": "Test campaign",
        "max_leads": 10,
        "channels": ["manual"],
        "discovery_seeds": [],
        "status": "draft",
        "stage": "discovery",
        "goal_type": "learn",
        "icp_preset_id": "default",
        "source_preset_id": "dynamic-discovery",
        "source_input": "residential painters Toronto",
        "source_inputs": {},
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
    }
