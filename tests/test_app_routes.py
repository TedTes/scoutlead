from app.main import app


def test_territories_route_is_registered_when_scheduler_is_disabled() -> None:
    paths = app.openapi()["paths"]

    assert "/territories" in paths
    assert "/discovery-runs/{run_id}/source-items" in paths
    assert "/discovery-runs/{run_id}/source-items/{source_item_id}/review" in paths
