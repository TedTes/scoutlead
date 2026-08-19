from __future__ import annotations

from icp.repository import ICPPresetRepository
from icp.schemas import ICPPreset


class ICPPresetService:
    def __init__(self, repository: ICPPresetRepository | None = None) -> None:
        self.repository = repository or ICPPresetRepository()

    def list(self) -> list[ICPPreset]:
        return self.repository.list()

    def get(self, preset_id: str | None) -> ICPPreset:
        return self.repository.get(preset_id)
