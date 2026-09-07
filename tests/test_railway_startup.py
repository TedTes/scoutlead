from scripts.start_railway_service import _service_kind


def test_railway_service_name_routes_web_to_static_server(monkeypatch) -> None:
    monkeypatch.delenv("SCOUTLEAD_SERVICE", raising=False)
    monkeypatch.delenv("SERVICE_TYPE", raising=False)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "web")

    assert _service_kind() == "web"


def test_explicit_service_kind_still_wins(monkeypatch) -> None:
    monkeypatch.setenv("SCOUTLEAD_SERVICE", "worker")
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "web")

    assert _service_kind() == "worker"
