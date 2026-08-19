from __future__ import annotations

from typing import Any

from leads.schemas import LeadRead
from tools.base import ToolResult, ToolSlot, measured_tool_result


class PublicPageSignalTool:
    name = "public_page_signals"
    slot = ToolSlot.SIGNAL

    def run(self, context: dict[str, Any]) -> ToolResult:
        lead = LeadRead.model_validate(context["lead"])

        def action() -> list[dict[str, str]]:
            signals = []
            if lead.research:
                signals.extend({"kind": "fit_signal", "value": signal} for signal in lead.research.signals)
                signals.extend(
                    {"kind": "pain_indicator", "value": signal}
                    for signal in lead.research.pain_indicators
                )
            return signals

        source_urls = []
        if lead.website_url:
            source_urls.append(lead.website_url)
        if lead.research:
            source_urls.extend(lead.research.sources)
        return measured_tool_result(
            provider="website_inspection",
            slot=self.slot,
            confidence=lead.research.confidence if lead.research else 0,
            source_urls=list(dict.fromkeys(source_urls)),
            action=action,
        )
