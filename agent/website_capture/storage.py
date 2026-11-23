from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from website_capture.contracts import StoredArtifact


class LocalArtifactStore:
    """Filesystem adapter; replaceable with R2/S3 without changing capture logic."""

    key = "local_filesystem"

    def __init__(self, root: str | Path = "artifacts/website-captures") -> None:
        self.root = Path(root).expanduser().resolve()

    def put(
        self,
        *,
        business_id: str,
        name: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact:
        safe_business_id = _safe_segment(business_id)
        safe_name = _safe_segment(name)
        target = self.root / safe_business_id / safe_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return StoredArtifact(
            uri=target.as_uri(),
            content_type=content_type,
            size_bytes=len(content),
        )

    def put_json(
        self,
        *,
        business_id: str,
        name: str,
        payload: dict[str, Any],
    ) -> StoredArtifact:
        return self.put(
            business_id=business_id,
            name=name,
            content=json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip(".-")
    if not cleaned:
        raise ValueError("artifact path segment is empty")
    return cleaned[:180]
