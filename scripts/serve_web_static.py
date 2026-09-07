#!/usr/bin/env python3
from __future__ import annotations

import mimetypes
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1] / "web" / "dist"
INDEX_FILE = ROOT / "index.html"


class SpaStaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def _serve(self, *, head_only: bool = False) -> None:
        target = self._resolve_path()
        if target and target.is_file():
            self._send_file(target, head_only=head_only)
            return

        if not urlparse(self.path).path.startswith("/assets/") and INDEX_FILE.is_file():
            self._send_file(INDEX_FILE, head_only=head_only)
            return

        self.send_error(404, "Not found")

    def _resolve_path(self) -> Path | None:
        try:
            relative = unquote(urlparse(self.path).path).lstrip("/") or "index.html"
            resolved = (ROOT / relative).resolve()
        except ValueError:
            return None

        if ROOT.resolve() not in [resolved, *resolved.parents]:
            return None
        return resolved

    def _send_file(self, path: Path, *, head_only: bool) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header(
            "Cache-Control",
            "no-cache" if path == INDEX_FILE else "public, max-age=31536000, immutable",
        )
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if head_only:
            return
        with path.open("rb") as file:
            self.copyfile(file, self.wfile)


def main() -> None:
    if not INDEX_FILE.is_file():
        raise SystemExit(f"web build output not found at {INDEX_FILE}")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "4173"))
    server = ThreadingHTTPServer((host, port), SpaStaticHandler)
    print(f"ScoutLead web listening on http://{host}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
