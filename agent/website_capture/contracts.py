from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ViewportCapture:
    name: str
    width: int
    height: int
    screenshot: bytes
    metrics: dict[str, float | int | bool | str | None]


@dataclass(frozen=True)
class WebsiteCaptureResult:
    requested_url: str
    final_url: str
    captured_at: str
    title: str | None
    viewports: list[ViewportCapture]
    page_metrics: dict[str, float | int | bool | str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredArtifact:
    uri: str
    content_type: str
    size_bytes: int


class BrowserCaptureProvider(Protocol):
    key: str

    def capture(self, url: str) -> WebsiteCaptureResult: ...


class ArtifactStore(Protocol):
    key: str

    def put(
        self,
        *,
        business_id: str,
        name: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact: ...


class WebsiteVisionModel(Protocol):
    key: str
    version: str

    def assess(
        self,
        *,
        capture: WebsiteCaptureResult,
        artifact_uris: dict[str, str],
    ) -> dict[str, Any] | None: ...


def capture_without_screenshots(capture: WebsiteCaptureResult) -> dict[str, Any]:
    payload = asdict(capture)
    for viewport in payload["viewports"]:
        viewport.pop("screenshot", None)
    return payload
