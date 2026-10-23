import httpx

from territories.geocoding import MarketGeocoder


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_market_geocoder_resolves_city_outside_launch_cache(monkeypatch) -> None:
    monkeypatch.setattr(
        "territories.geocoding.httpx.get",
        lambda *args, **kwargs: FakeResponse(
            [
                {
                    "place_id": 123,
                    "lat": "30.2672",
                    "lon": "-97.7431",
                    "display_name": "Austin, Travis County, Texas, United States",
                }
            ]
        ),
    )

    result = MarketGeocoder(timeout_seconds=1).resolve("Austin, TX")

    assert result is not None
    assert result.latitude == 30.2672
    assert result.longitude == -97.7431
    assert result.provider == "openstreetmap_nominatim"


def test_market_geocoder_rejects_invalid_provider_coordinates(monkeypatch) -> None:
    monkeypatch.setattr(
        "territories.geocoding.httpx.get",
        lambda *args, **kwargs: FakeResponse(
            [{"place_id": 123, "lat": "130", "lon": "-97.7431"}]
        ),
    )

    assert MarketGeocoder(timeout_seconds=1).resolve("Invalid City") is None


def test_market_geocoder_retries_after_transient_provider_failure(monkeypatch) -> None:
    calls = 0

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary outage")
        return FakeResponse(
            [
                {
                    "place_id": 456,
                    "lat": "45.5019",
                    "lon": "-73.5674",
                    "display_name": "Montreal, Quebec, Canada",
                }
            ]
        )

    monkeypatch.setattr("territories.geocoding.httpx.get", get)
    geocoder = MarketGeocoder(timeout_seconds=1)

    assert geocoder.resolve("Montreal, QC") is None
    assert geocoder.resolve("Montreal, QC") is not None
    assert calls == 2


def test_market_geocoder_search_returns_canonical_choices_and_caches_selection(
    monkeypatch,
) -> None:
    calls = 0

    def get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse(
            [
                {
                    "place_id": 123,
                    "lat": "30.2672",
                    "lon": "-97.7431",
                    "display_name": "Austin, Travis County, Texas, United States",
                    "address": {"country_code": "us"},
                },
                {
                    "place_id": 456,
                    "lat": "45.5019",
                    "lon": "-73.5674",
                    "display_name": "Montreal, Quebec, Canada",
                    "address": {"country_code": "ca"},
                },
            ]
        )

    monkeypatch.setattr("territories.geocoding.httpx.get", get)
    geocoder = MarketGeocoder(timeout_seconds=1)

    results = geocoder.search("Austin", limit=2)
    selected = geocoder.resolve(results[0].label)

    assert [result.country_code for result in results] == ["us", "ca"]
    assert selected == results[0]
    assert calls == 1
