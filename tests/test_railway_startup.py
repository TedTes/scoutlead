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


def test_railway_services_use_dedicated_runtime_images() -> None:
    root = Path(__file__).parents[1]
    api_config = json.loads(
        (root / "deploy" / "railway" / "api.railway.json").read_text()
    )
    worker_config = json.loads(
        (root / "deploy" / "railway" / "worker.railway.json").read_text()
    )
    web_config = json.loads(
        (root / "deploy" / "railway" / "web.railway.json").read_text()
    )

    assert api_config["build"]["dockerfilePath"] == "Dockerfile.api"
    assert worker_config["build"]["dockerfilePath"] == "Dockerfile.worker"
    assert web_config["build"]["dockerfilePath"] == "Dockerfile"

    api_dockerfile = (root / "Dockerfile.api").read_text()
    worker_dockerfile = (root / "Dockerfile.worker").read_text()
    web_dockerfile = (root / "web" / "Dockerfile").read_text()

    assert "playwright install" not in api_dockerfile
    assert "playwright install --with-deps chromium" in worker_dockerfile
    assert "[website-capture]" in worker_dockerfile
    assert "FROM node:24-slim" in web_dockerfile
