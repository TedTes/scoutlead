from __future__ import annotations

from typing import Any

from tools.base import ToolResult, ToolSlot, measured_tool_result


class AppStoreReviewsSignalTool:
    name = "app_store_reviews"
    slot = ToolSlot.SIGNAL

    def run(self, context: dict[str, Any]) -> ToolResult:
        return measured_tool_result(
            provider="apple_app_store",
            slot=self.slot,
            confidence=0,
            source_urls=[],
            raw={"configured": False, "usage": "aggregate product insight only"},
            action=lambda: [],
        )
