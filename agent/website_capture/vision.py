from __future__ import annotations

from typing import Any

from website_capture.contracts import WebsiteCaptureResult


class NoopWebsiteVisionModel:
    """Default adapter: capture works locally without a hosted vision model."""

    key = "none"
    version = "none"

    def assess(
        self,
        *,
        capture: WebsiteCaptureResult,
        artifact_uris: dict[str, str],
    ) -> dict[str, Any] | None:
        return None
