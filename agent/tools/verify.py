from __future__ import annotations

import re
from typing import Any

from tools.base import ToolResult, ToolSlot, measured_tool_result

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailSyntaxVerifyTool:
    name = "email_syntax"
    slot = ToolSlot.VERIFY

    def run(self, context: dict[str, Any]) -> ToolResult:
        email = str(context.get("email") or "")

        def action() -> dict[str, str]:
            verdict = "valid" if EMAIL_RE.match(email) else "invalid"
            return {"email": email, "verdict": verdict}

        return measured_tool_result(
            provider="local",
            slot=self.slot,
            confidence=80 if EMAIL_RE.match(email) else 20,
            action=action,
        )
