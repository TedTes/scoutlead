from __future__ import annotations

import json
from pathlib import Path

from shared.errors import NotFoundError
from source_presets.schemas import SourcePreset


class SourcePresetRepository:
    def __init__(self, preset_dir: Path | None = None) -> None:
        self.preset_dir = preset_dir or Path(__file__).parent / "presets"

    def list(self) -> list[SourcePreset]:
        presets = []
        for path in sorted(self.preset_dir.glob("*.json")):
            presets.append(self._load(path))
        return presets

    def get(self, preset_id: str | None) -> SourcePreset:
        resolved_id = preset_id or "default-web-validation"
        path = self.preset_dir / f"{resolved_id}.json"
        if not path.exists():
            raise NotFoundError("source preset not found", {"source_preset_id": resolved_id})
        return self._load(path)

    @staticmethod
    def _load(path: Path) -> SourcePreset:
        return SourcePreset.model_validate(json.loads(path.read_text()))
