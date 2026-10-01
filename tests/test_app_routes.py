from app.main import app


def test_territories_route_is_registered_when_scheduler_is_disabled() -> None:
    paths = app.openapi()["paths"]

    assert "/territories" in paths
