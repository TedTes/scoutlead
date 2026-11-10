import json
from pathlib import Path

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


def test_api_runs_database_migrations_before_deploy() -> None:
    config_path = Path(__file__).parents[1] / "deploy" / "railway" / "api.railway.json"
    config = json.loads(config_path.read_text())

    command = config["deploy"]["preDeployCommand"]
    assert command.startswith("PYTHONPATH=agent alembic upgrade head")
    assert "python scripts/seed_trade_catalog.py" in command


def test_trade_catalog_is_included_in_railway_build_context() -> None:
    root = Path(__file__).parents[1]
    dockerignore = (root / ".dockerignore").read_text().splitlines()
    gitignore = (root / ".gitignore").read_text().splitlines()

    assert "!data/seeds" in dockerignore
    assert "!data/seeds/canonical-trade-catalog.json" in dockerignore
    assert "!/data/seeds/canonical-trade-catalog.json" in gitignore


def test_trade_catalog_changes_trigger_backend_release() -> None:
    workflow_path = Path(__file__).parents[1] / ".github" / "workflows" / "ci-release.yml"
    workflow = workflow_path.read_text()

    assert "data/seeds/canonical-trade-catalog\\.json" in workflow
    assert "seed_trade_catalog" in workflow
    assert workflow.count("\\.gitignore") >= 2
