from __future__ import annotations

from typing import Any

from leads.schemas import LeadRead
from tools.base import ToolResult, ToolSlot, measured_tool_result


class PublicEmailContactTool:
    name = "public_email"
    slot = ToolSlot.CONTACT

    def run(self, context: dict[str, Any]) -> ToolResult:
        lead = LeadRead.model_validate(context["lead"])

        def action() -> dict[str, str] | None:
            email = lead.contact_email or (lead.research.contact_email if lead.research else None)
            if not email:
                return None
            return {"email": email, "source": "public_page_or_seed"}

        source_urls = []
        if lead.website_url:
            source_urls.append(lead.website_url)
        if lead.research:
            source_urls.extend(lead.research.sources)
        return measured_tool_result(
            provider="website_inspection",
            slot=self.slot,
            confidence=75 if lead.contact_email else 65,
            source_urls=list(dict.fromkeys(source_urls)),
            action=action,
        )
