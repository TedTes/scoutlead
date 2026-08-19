from fastapi import APIRouter

from icp.schemas import ICPPreset
from icp.service import ICPPresetService

router = APIRouter(prefix="/icp-presets", tags=["icp-presets"])


@router.get("", response_model=list[ICPPreset])
def list_icp_presets() -> list[ICPPreset]:
    return ICPPresetService().list()
