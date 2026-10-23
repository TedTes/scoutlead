from app.main import app


def test_audience_routes_are_registered_when_scheduler_is_disabled() -> None:
    paths = app.openapi()["paths"]

    assert "/territories" not in paths
    assert "/audiences/options" in paths
    assert "/audiences/places" in paths
    assert "/audiences" in paths
    assert "/audiences/from-resolution" in paths
    assert "delete" in paths["/audiences/{audience_id}"]
    assert "/audiences/{audience_id}/current-batch" in paths
    assert "post" in paths["/outreach-packages/{package_id}/message"]
    assert "post" in paths["/products/from-profile"]
    assert "/discovery-runs/{run_id}/source-items" in paths
    assert "/discovery-runs/{run_id}/source-items/{source_item_id}/review" in paths
