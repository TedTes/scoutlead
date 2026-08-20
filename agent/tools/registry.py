from __future__ import annotations

from typing import Callable

from icp.schemas import SlotConfig
from tools.base import ToolAdapter, ToolSlot
from tools.contact import PublicEmailContactTool
from tools.signal.public_page import PublicPageSignalTool
from tools.verify import EmailSyntaxVerifyTool

# Which provider fills which slot is ICP-preset data, not code: this is the one
# place that maps a (slot, provider name) pair from preset JSON to the adapter
# that implements it. Swapping or adding a provider for a slot is a change here
# plus a preset edit -- workflows never reference a provider by name.
_FACTORIES: dict[tuple[ToolSlot, str], Callable[[], ToolAdapter]] = {
    (ToolSlot.CONTACT, "website_inspection"): PublicEmailContactTool,
    (ToolSlot.VERIFY, "local"): EmailSyntaxVerifyTool,
    (ToolSlot.SIGNAL, "website_inspection"): PublicPageSignalTool,
}


def resolve_tools(config: SlotConfig) -> list[ToolAdapter]:
    tools: list[ToolAdapter] = []
    for tool_config in config.tools:
        if not tool_config.enabled:
            continue
        factory = _FACTORIES.get((config.slot, tool_config.provider))
        if factory is None:
            raise ValueError(
                f"No provider registered for slot={config.slot.value!r} provider={tool_config.provider!r}"
            )
        tools.append(factory())
    return tools
