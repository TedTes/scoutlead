#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def main() -> None:
    service = _service_kind()
    if service == "worker":
        command = [sys.executable, "-m", "job_queue.worker"]
    else:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            os.environ.get("PORT", "8000"),
        ]

    print(f"Starting ScoutLead {service}: {' '.join(command)}", flush=True)
    os.execvp(command[0], command)


def _service_kind() -> str:
    explicit = os.environ.get("SCOUTLEAD_SERVICE") or os.environ.get("SERVICE_TYPE")
    if explicit:
        return explicit.strip().lower()

    railway_service = os.environ.get("RAILWAY_SERVICE_NAME", "").strip().lower()
    if "worker" in railway_service:
        return "worker"
    return "api"


if __name__ == "__main__":
    main()
