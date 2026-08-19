from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Any, Callable, Protocol, TypeVar


class ToolSlot(StrEnum):
    DISCOVERY = "discovery"
    CONTACT = "contact"
    VERIFY = "verify"
    SIGNAL = "signal"


class ToolExecutionMode(StrEnum):
    ACCUMULATE = "accumulate"
    FIRST_GOOD = "first_good"


@dataclass(frozen=True)
class ToolResult:
    provider: str
    slot: ToolSlot
    data: Any
    confidence: int = 0
    source_urls: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return self.data is None or self.data == [] or self.data == {}

    def meets_confidence(self, threshold: int) -> bool:
        return not self.is_empty and self.confidence >= threshold

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "slot": self.slot.value,
            "data": self.data,
            "confidence": self.confidence,
            "source_urls": self.source_urls,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "raw": self.raw,
        }


class ToolAdapter(Protocol):
    name: str
    slot: ToolSlot

    def run(self, context: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


T = TypeVar("T")


def measured_tool_result(
    *,
    provider: str,
    slot: ToolSlot,
    confidence: int,
    source_urls: list[str] | None = None,
    cost_usd: float = 0.0,
    raw: dict[str, Any] | None = None,
    action: Callable[[], T],
) -> ToolResult:
    start = perf_counter()
    data = action()
    latency_ms = round((perf_counter() - start) * 1000)
    return ToolResult(
        provider=provider,
        slot=slot,
        data=data,
        confidence=confidence,
        source_urls=source_urls or [],
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        raw=raw or {},
    )
