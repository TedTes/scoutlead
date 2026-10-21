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
