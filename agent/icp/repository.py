from __future__ import annotations

import json
from pathlib import Path

from icp.schemas import BudgetConfig, ICPPreset, SlotConfig, ToolConfig
from tools.base import ToolExecutionMode, ToolSlot


class ICPPresetRepository:
    def __init__(self, presets_dir: Path | None = None) -> None:
        self.presets_dir = presets_dir or Path(__file__).with_name("presets")

    def list(self) -> list[ICPPreset]:
        presets: list[ICPPreset] = []
        if self.presets_dir.exists():
            for path in sorted(self.presets_dir.glob("*.json")):
                presets.append(ICPPreset.model_validate(json.loads(path.read_text())))
        if not presets:
            presets.append(default_preset())
        return presets

    def get(self, preset_id: str | None) -> ICPPreset:
        presets = self.list()
        if preset_id:
            for preset in presets:
                if preset.id == preset_id:
                    return preset
        return presets[0]


def default_preset() -> ICPPreset:
    return ICPPreset(
        id="default-web-validation",
        name="Default web validation",
        description="Generic validation preset using web search, public pages, and approved email only.",
        budget=BudgetConfig(max_cost_usd=5.0, max_tool_calls=50),
        slots=[
            SlotConfig(
                slot=ToolSlot.DISCOVERY,
                mode=ToolExecutionMode.ACCUMULATE,
                tools=[ToolConfig(name="web_search", provider="configured_search")],
                confidence_threshold=55,
                target_count=25,
            ),
            SlotConfig(
                slot=ToolSlot.CONTACT,
                mode=ToolExecutionMode.FIRST_GOOD,
                tools=[ToolConfig(name="public_email", provider="website_inspection")],
                confidence_threshold=70,
                target_count=1,
            ),
            SlotConfig(
                slot=ToolSlot.VERIFY,
                mode=ToolExecutionMode.FIRST_GOOD,
                tools=[ToolConfig(name="email_syntax", provider="local")],
                confidence_threshold=70,
                target_count=1,
            ),
            SlotConfig(
                slot=ToolSlot.SIGNAL,
                mode=ToolExecutionMode.ACCUMULATE,
                tools=[ToolConfig(name="public_page_signals", provider="website_inspection")],
                confidence_threshold=55,
                target_count=5,
            ),
        ],
    )
