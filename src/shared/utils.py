from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import json
from typing import Any
from uuid import uuid4


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if trimmed.startswith(("http://", "https://")):
        return trimmed
    return f"https://{trimmed}"


def normalize_text(value: str | None) -> str:
    return " ".join((value or "").split())


def truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[: max_length - 3]}..."


def enum_value(value: Enum | str) -> str:
    return value.value if isinstance(value, Enum) else value


def keyword_hits(text: str, keywords: list[str]) -> list[str]:
    lower = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lower]


def safe_json_loads(value: str) -> Any | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None
