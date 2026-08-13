from connections.routes import list_connection_status


def test_connection_status_reports_runtime_capabilities() -> None:
    statuses = list_connection_status()

    assert {status.category for status in statuses} >= {
        "persistence",
        "reasoning",
        "discovery",
        "outreach",
    }
