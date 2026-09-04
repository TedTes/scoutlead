#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


SKIP_MESSAGE = "no changes detected in watch paths, build will skip"


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print("usage: scripts/railway_up_ci.py railway up ...", file=sys.stderr)
        return 2

    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    skip_detected = False

    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        if SKIP_MESSAGE not in line:
            continue
        skip_detected = True
        time.sleep(2)
        if process.poll() is None:
            _terminate_process_group(process)
        break

    status = process.wait()
    if skip_detected:
        print(
            "Railway reported no watch-path changes; "
            "treating this service deploy as a successful skip."
        )
        return 0
    return status


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)


if __name__ == "__main__":
    raise SystemExit(main())
