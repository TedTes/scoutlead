from __future__ import annotations

from pydantic import BaseModel


class ToolHitRate(BaseModel):
    provider: str
    slot: str
    calls: int
    accepted: int
    total_cost_usd: float
    average_latency_ms: int


def calculate_hit_rates(tool_results: list[dict]) -> list[ToolHitRate]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for result in tool_results:
        key = (str(result.get("provider")), str(result.get("slot")))
        grouped.setdefault(key, []).append(result)

    rates: list[ToolHitRate] = []
    for (provider, slot), rows in grouped.items():
        calls = len(rows)
        accepted = sum(1 for row in rows if int(row.get("confidence") or 0) >= 70)
        rates.append(
            ToolHitRate(
                provider=provider,
                slot=slot,
                calls=calls,
                accepted=accepted,
                total_cost_usd=round(sum(float(row.get("cost_usd") or 0) for row in rows), 4),
                average_latency_ms=round(
                    sum(int(row.get("latency_ms") or 0) for row in rows) / calls
                )
                if calls
                else 0,
            )
        )
    return rates
