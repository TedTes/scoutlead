from app.main import app


def test_territories_route_is_registered_when_scheduler_is_disabled() -> None:
    paths = app.openapi()["paths"]

    assert "/territories" in paths
    assert "/profiles/options" in paths
    assert "/profiles" in paths
    assert "delete" in paths["/profiles/{profile_id}"]
    assert "/profiles/{profile_id}/current-batch" in paths
    assert "post" in paths["/products/from-profile"]
    assert "/discovery-runs/{run_id}/source-items" in paths
    assert "/discovery-runs/{run_id}/source-items/{source_item_id}/review" in paths
