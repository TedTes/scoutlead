#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_DOT_PATHS = {"build.watchPatterns"}
PROJECT_FLAG_UNSUPPORTED_MARKERS = (
    "unexpected argument '--project'",
    "unexpected argument",
    "unknown option",
    "unrecognized option",
    "found argument '--project'",
)


@dataclass(frozen=True)
class RailwayServiceConfig:
    env_var: str
    root_directory: str
    manifest: Path


SERVICES = {
    "api": RailwayServiceConfig(
        env_var="RAILWAY_API_SERVICE",
        root_directory="/",
        manifest=ROOT / "deploy/railway/api.railway.json",
    ),
    "worker": RailwayServiceConfig(
        env_var="RAILWAY_WORKER_SERVICE",
        root_directory="/",
        manifest=ROOT / "deploy/railway/worker.railway.json",
    ),
    "web": RailwayServiceConfig(
        env_var="RAILWAY_WEB_SERVICE",
        root_directory="/",
        manifest=ROOT / "deploy/railway/web.railway.json",
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply repo-owned Railway service settings before deployment."
    )
    parser.add_argument(
        "--service",
        action="append",
        choices=sorted(SERVICES),
        help="Service config to apply. Defaults to all services.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Railway CLI commands without running them.",
    )
    parser.add_argument(
        "--message",
        help="Railway environment edit message. Defaults to the current GitHub SHA when present.",
    )
    args = parser.parse_args()

    project = os.environ.get("RAILWAY_PROJECT_ID")
    environment = os.environ.get("RAILWAY_ENVIRONMENT")
    if not args.dry_run and not environment:
        print("RAILWAY_ENVIRONMENT is required to apply Railway service config", file=sys.stderr)
        return 2

    message = args.message or _default_message()
    selected_services = args.service or sorted(SERVICES)
    for service_key in selected_services:
        service_config = SERVICES[service_key]
        service = _service_name(service_config, dry_run=args.dry_run)
        if service is None:
            return 2

        manifest = _load_manifest(service_config.manifest)
        settings = [("source.rootDirectory", service_config.root_directory)]
        settings.extend(_manifest_settings(manifest))

        for dot_path, value in settings:
            required = dot_path not in OPTIONAL_DOT_PATHS
            status = _apply_setting(
                project=project or "$RAILWAY_PROJECT_ID",
                environment=environment or "$RAILWAY_ENVIRONMENT",
                service=service,
                dot_path=dot_path,
                value=value,
                message=message,
                dry_run=args.dry_run,
            )
            if status == 0:
                continue
            if not required:
                print(
                    f"::warning::Railway rejected optional setting {service_key}.{dot_path}; "
                    "continuing because start/root config has already been applied.",
                    file=sys.stderr,
                )
                continue
            return status

    return 0


def _service_name(service_config: RailwayServiceConfig, *, dry_run: bool) -> str | None:
    service = os.environ.get(service_config.env_var)
    if service:
        return service
    if dry_run:
        return f"${service_config.env_var}"

    print(f"{service_config.env_var} is required to apply Railway service config", file=sys.stderr)
    return None


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _manifest_settings(manifest: dict[str, Any]) -> list[tuple[str, Any]]:
    settings: list[tuple[str, Any]] = []
    for section in ("build", "deploy"):
        values = manifest.get(section, {})
        if not isinstance(values, dict):
            raise TypeError(f"{section} in Railway manifest must be an object")
        for key, value in values.items():
            if value is None:
                continue
            settings.append((f"{section}.{key}", value))
    return settings


def _apply_setting(
    *,
    project: str,
    environment: str,
    service: str,
    dot_path: str,
    value: Any,
    message: str,
    dry_run: bool,
) -> int:
    command = [
        "railway",
        "environment",
        "edit",
        "--project",
        project,
        "--environment",
        environment,
        "--service-config",
        service,
        dot_path,
        _format_value(value),
        "--message",
        message,
    ]
    if dry_run:
        print("+ " + " ".join(shlex.quote(part) for part in command))
        return 0

    completed = _run_command(command)
    if completed.returncode == 0 or not _project_flag_was_rejected(completed.stdout):
        if completed.returncode != 0 and _looks_unauthorized(completed.stdout):
            _print_auth_error()
        return completed.returncode

    fallback_command = _without_project_flag(command)
    print(
        "::warning::Railway CLI rejected --project for environment edit; "
        "retrying with token-scoped project context.",
        file=sys.stderr,
    )
    return _run_command(fallback_command).returncode


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    return completed


def _project_flag_was_rejected(output: str) -> bool:
    normalized = output.lower()
    return "--project" in normalized and any(
        marker in normalized for marker in PROJECT_FLAG_UNSUPPORTED_MARKERS
    )


def _without_project_flag(command: list[str]) -> list[str]:
    without_project: list[str] = []
    skip_next = False
    for part in command:
        if skip_next:
            skip_next = False
            continue
        if part == "--project":
            skip_next = True
            continue
        without_project.append(part)
    return without_project


def _looks_unauthorized(output: str) -> bool:
    return "unauthorized" in output.lower()


def _print_auth_error() -> None:
    if os.environ.get("RAILWAY_API_TOKEN"):
        token_hint = "Check that RAILWAY_API_TOKEN belongs to the Railway workspace/project."
    else:
        token_hint = (
            "Project deploy tokens may not be allowed to edit service config. "
            "Add a Railway account/workspace token as GitHub secret RAILWAY_API_TOKEN, "
            "or set the service root directories and start commands manually in Railway."
        )
    print(f"::error::{token_hint}", file=sys.stderr)


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | dict):
        return json.dumps(value, separators=(",", ":"))
    return str(value)


def _default_message() -> str:
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return f"github:{sha} railway service config"
    return "sync Railway service config from repo"


if __name__ == "__main__":
    raise SystemExit(main())
