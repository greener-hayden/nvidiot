"""FastAPI routes — thin wrappers around nvapi.service."""

import logging
import os
import signal

from fastapi import APIRouter, Depends, HTTPException

from nvapi import service
from nvapi.constants import SETTING_IDS, NvAPI_Status
from nvapi.ffi import NvAPIError

from .auth import require_token
from .throttle import throttle_writes
from .models import (
    AppInfo,
    AppRequest,
    BaseProfileDetail,
    CreateProfileRequest,
    DesktopPresetRequest,
    DisplayInfo,
    GamingPresetRequest,
    GPUInfo,
    ProfileDetail,
    ProfileSummary,
    SetResolutionRequest,
    SetSaturationRequest,
    SetSettingRequest,
    SettingIdEntry,
    SettingInfo,
)

logger = logging.getLogger("nvidiot")

read_router = APIRouter()
write_router = APIRouter(
    dependencies=[Depends(require_token), Depends(throttle_writes)]
)

_STATUS_TO_HTTP = {
    NvAPI_Status.NVAPI_PROFILE_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_SETTING_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_EXECUTABLE_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_SETTING_NOT_FOUND_NO_DEFAULT: 404,
    NvAPI_Status.NVAPI_INVALID_ARGUMENT: 400,
    NvAPI_Status.NVAPI_PROFILE_NAME_IN_USE: 409,
    NvAPI_Status.NVAPI_EXECUTABLE_ALREADY_IN_USE: 409,
}


def _handle(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except NvAPIError as e:
        logger.warning("NvAPIError in %s: %s", func.__name__, e)
        code = _STATUS_TO_HTTP.get(e.status, 500)
        raise HTTPException(status_code=code, detail="operation failed") from e


# ------------------------------------------------------------------
# GPU (read)
# ------------------------------------------------------------------
@read_router.get("/gpu", response_model=list[GPUInfo])
def get_gpus():
    return _handle(service.list_gpus)


# ------------------------------------------------------------------
# Base (global) profile (read)
# ------------------------------------------------------------------
@read_router.get("/base", response_model=BaseProfileDetail)
def get_base_profile():
    return _handle(service.get_base_profile)


@read_router.get("/base/settings/{setting_id}", response_model=SettingInfo)
def get_base_setting(setting_id: int):
    return _handle(service.get_base_setting, setting_id)


# ------------------------------------------------------------------
# Base (global) profile (write)
# ------------------------------------------------------------------
@write_router.put("/base/settings/{setting_id}", response_model=SettingInfo)
def set_base_setting(setting_id: int, body: SetSettingRequest):
    return _handle(service.set_base_setting, setting_id, body.value)


@write_router.delete("/base/settings/{setting_id}", status_code=204)
def delete_base_setting(setting_id: int):
    _handle(service.delete_base_setting, setting_id)


# ------------------------------------------------------------------
# Profiles (read)
# ------------------------------------------------------------------
@read_router.get("/profiles", response_model=list[str])
def list_profiles():
    return _handle(service.list_profiles)


@read_router.get("/profiles/{profile_name}", response_model=ProfileDetail)
def get_profile(profile_name: str):
    return _handle(service.get_profile, profile_name)


# ------------------------------------------------------------------
# Profiles (write)
# ------------------------------------------------------------------
@write_router.post("/profiles", response_model=ProfileSummary, status_code=201)
def create_profile(body: CreateProfileRequest):
    return _handle(service.create_profile, body.name)


@write_router.delete("/profiles/{profile_name}", status_code=204)
def delete_profile(profile_name: str):
    _handle(service.delete_profile, profile_name)


# ------------------------------------------------------------------
# Profile settings (read)
# ------------------------------------------------------------------
@read_router.get(
    "/profiles/{profile_name}/settings/{setting_id}", response_model=SettingInfo
)
def get_profile_setting(profile_name: str, setting_id: int):
    return _handle(service.get_setting, profile_name, setting_id)


# ------------------------------------------------------------------
# Profile settings (write)
# ------------------------------------------------------------------
@write_router.put(
    "/profiles/{profile_name}/settings/{setting_id}", response_model=SettingInfo
)
def set_profile_setting(
    profile_name: str, setting_id: int, body: SetSettingRequest
):
    return _handle(service.set_setting, profile_name, setting_id, body.value)


@write_router.delete("/profiles/{profile_name}/settings/{setting_id}", status_code=204)
def delete_profile_setting(profile_name: str, setting_id: int):
    _handle(service.delete_setting, profile_name, setting_id)


# ------------------------------------------------------------------
# Profile applications (read)
# ------------------------------------------------------------------
@read_router.get("/profiles/{profile_name}/apps", response_model=list[AppInfo])
def list_apps(profile_name: str):
    return _handle(service.list_apps, profile_name)


# ------------------------------------------------------------------
# Profile applications (write)
# ------------------------------------------------------------------
@write_router.post("/profiles/{profile_name}/apps", status_code=201)
def add_app(profile_name: str, body: AppRequest):
    _handle(service.add_app, profile_name, body.exe)


@write_router.delete("/profiles/{profile_name}/apps", status_code=204)
def remove_app(profile_name: str, body: AppRequest):
    _handle(service.remove_app, profile_name, body.exe)


# ------------------------------------------------------------------
# Display control (read)
# ------------------------------------------------------------------
@read_router.get("/display", response_model=DisplayInfo)
def get_display():
    return _handle(service.get_display_info)


# ------------------------------------------------------------------
# Display control (write)
# ------------------------------------------------------------------
@write_router.put("/display/saturation", response_model=DisplayInfo)
def set_saturation(body: SetSaturationRequest):
    return _handle(service.set_saturation, body.level)


@write_router.put("/display/resolution", response_model=DisplayInfo)
def set_resolution(body: SetResolutionRequest):
    return _handle(service.set_resolution, body.width, body.height, body.refresh, body.stretch)


@write_router.post("/display/preset/gaming", response_model=DisplayInfo)
def gaming_preset(body: GamingPresetRequest):
    return _handle(
        service.apply_gaming_preset, body.width, body.height, body.saturation, body.refresh, body.stretch
    )


@write_router.post("/display/preset/desktop", response_model=DisplayInfo)
def desktop_preset(body: DesktopPresetRequest):
    return _handle(service.apply_desktop_preset, body.saturation)


# ------------------------------------------------------------------
# Setting ID registry (read)
# ------------------------------------------------------------------
@read_router.get("/settings/ids", response_model=list[SettingIdEntry])
def list_setting_ids():
    return [
        {"id": sid, "idHex": f"0x{sid:08X}", "name": name}
        for sid, name in sorted(SETTING_IDS.items())
    ]


# ------------------------------------------------------------------
# Shutdown (write)
# ------------------------------------------------------------------
@write_router.post("/shutdown", status_code=202)
def shutdown():
    os.kill(os.getpid(), signal.SIGTERM)
    return {"detail": "shutting down"}
