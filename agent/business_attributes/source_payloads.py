from __future__ import annotations

import re


SOURCE_PAYLOAD_PREFIX = "__source_payload__:"


def source_payload_attribute_key(source_provider: str | None) -> str:
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        (source_provider or "unknown").strip().lower(),
    ).strip("_")
    return f"{SOURCE_PAYLOAD_PREFIX}{normalized or 'unknown'}"


def is_source_payload_attribute(attribute_key: str | None) -> bool:
    return bool(attribute_key and attribute_key.startswith(SOURCE_PAYLOAD_PREFIX))
