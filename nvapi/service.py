"""Pythonic wrappers around NVAPI FFI, returning plain dicts."""

import logging
import subprocess
from contextlib import contextmanager
from typing import Generator

from . import ffi
from .constants import NVDRS_DWORD_TYPE, NVDRS_WSTRING_TYPE, NvAPI_Status, SETTING_IDS, SETTING_VALUE_RANGES

logger = logging.getLogger("nvidiot")

# GlazeWM process path — captured before killing so we can restart it
_glazewm_path: str | None = None


@contextmanager
def drs_session(save_on_exit: bool = False) -> Generator[ffi.NvDRSSessionHandle, None, None]:
    session = ffi.DRS_CreateSession()
    try:
        ffi.DRS_LoadSettings(session)
        yield session
        if save_on_exit:
            ffi.DRS_SaveSettings(session)
    finally:
        ffi.DRS_DestroySession(session)


def _ensure_initialized() -> None:
    status = ffi.Initialize()
    if status != NvAPI_Status.NVAPI_OK:
        raise ffi.NvAPIError(status, "NvAPI_Initialize")


# ------------------------------------------------------------------
# GPU info
# ------------------------------------------------------------------
def list_gpus() -> list[dict]:
    _ensure_initialized()
    handles = ffi.EnumPhysicalGPUs()
    results = []
    for h in handles:
        name = ffi.GPU_GetFullName(h)
        try:
            thermal = ffi.GPU_GetThermalSettings(h)
            temp = thermal.sensor[0].currentTemp if thermal.count > 0 else None
        except ffi.NvAPIError:
            temp = None
        results.append({"name": name, "temperature_c": temp})
    return results


# ------------------------------------------------------------------
# Profile operations
# ------------------------------------------------------------------
def list_profiles() -> list[str]:
    _ensure_initialized()
    with drs_session() as session:
        count = ffi.DRS_GetNumProfiles(session)
        names = []
        for i in range(count):
            try:
                handle = ffi.DRS_EnumProfiles(session, i)
                info = ffi.DRS_GetProfileInfo(session, handle)
                names.append(info.profileName)
            except ffi.NvAPIError:
                break
        return names


def _get_all_settings(session, profile_handle) -> list[dict]:
    settings = []
    idx = 0
    while True:
        s = ffi.DRS_EnumSettings(session, profile_handle, idx)
        if s is None:
            break
        settings.append(_setting_to_dict(s))
        idx += 1
    return settings


def _get_all_apps(session, profile_handle) -> list[dict]:
    apps = []
    idx = 0
    while True:
        a = ffi.DRS_EnumApplications(session, profile_handle, idx)
        if a is None:
            break
        apps.append({
            "appName": a.appName,
            "userFriendlyName": a.userFriendlyName,
            "isPredefined": bool(a.isPredefined),
        })
        idx += 1
    return apps


def _setting_to_dict(s: ffi.NVDRS_SETTING) -> dict:
    setting_name = SETTING_IDS.get(s.settingId, s.settingName or f"0x{s.settingId:08X}")
    if s.settingType == NVDRS_DWORD_TYPE:
        value = s.currentValue.dwordValue
    elif s.settingType == NVDRS_WSTRING_TYPE:
        value = s.currentValue.wszValue
    else:
        value = s.currentValue.dwordValue
    return {
        "settingId": s.settingId,
        "settingIdHex": f"0x{s.settingId:08X}",
        "settingName": setting_name,
        "settingType": s.settingType,
        "currentValue": value,
        "isPredefined": bool(s.isCurrentPredefined),
    }


def get_profile(name: str) -> dict:
    _ensure_initialized()
    with drs_session() as session:
        handle = ffi.DRS_FindProfileByName(session, name)
        info = ffi.DRS_GetProfileInfo(session, handle)
        return {
            "profileName": info.profileName,
            "isPredefined": bool(info.isPredefined),
            "numOfApps": info.numOfApps,
            "numOfSettings": info.numOfSettings,
            "settings": _get_all_settings(session, handle),
            "applications": _get_all_apps(session, handle),
        }


def get_base_profile() -> dict:
    _ensure_initialized()
    with drs_session() as session:
        handle = ffi.DRS_GetBaseProfile(session)
        info = ffi.DRS_GetProfileInfo(session, handle)
        return {
            "profileName": info.profileName or "Base Profile",
            "isPredefined": True,
            "numOfSettings": info.numOfSettings,
            "settings": _get_all_settings(session, handle),
        }


def get_setting(profile_name: str, setting_id: int) -> dict:
    _ensure_initialized()
    with drs_session() as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        s = ffi.DRS_GetSetting(session, handle, setting_id)
        return _setting_to_dict(s)


def get_base_setting(setting_id: int) -> dict:
    _ensure_initialized()
    with drs_session() as session:
        handle = ffi.DRS_GetBaseProfile(session)
        s = ffi.DRS_GetSetting(session, handle, setting_id)
        return _setting_to_dict(s)


def _validate_setting_write(setting_id: int, value: int) -> None:
    if setting_id not in SETTING_IDS:
        raise ffi.NvAPIError(
            NvAPI_Status.NVAPI_INVALID_ARGUMENT,
            f"setting 0x{setting_id:08X} not in allowlist",
        )
    enum_type = SETTING_VALUE_RANGES.get(setting_id)
    if enum_type is not None:
        valid = {v.value for v in enum_type}
        if value not in valid:
            raise ffi.NvAPIError(
                NvAPI_Status.NVAPI_INVALID_ARGUMENT,
                f"value {value} not valid for {SETTING_IDS[setting_id]} (expected one of {sorted(valid)})",
            )


def set_setting(profile_name: str, setting_id: int, value: int) -> dict:
    _validate_setting_write(setting_id, value)
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        setting = ffi.NVDRS_SETTING()
        setting.version = ffi.NVDRS_SETTING_VER
        setting.settingId = setting_id
        setting.settingType = NVDRS_DWORD_TYPE
        setting.currentValue.dwordValue = value
        ffi.DRS_SetSetting(session, handle, setting)
        s = ffi.DRS_GetSetting(session, handle, setting_id)
        return _setting_to_dict(s)


def set_base_setting(setting_id: int, value: int) -> dict:
    _validate_setting_write(setting_id, value)
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_GetBaseProfile(session)
        setting = ffi.NVDRS_SETTING()
        setting.version = ffi.NVDRS_SETTING_VER
        setting.settingId = setting_id
        setting.settingType = NVDRS_DWORD_TYPE
        setting.currentValue.dwordValue = value
        ffi.DRS_SetSetting(session, handle, setting)
        s = ffi.DRS_GetSetting(session, handle, setting_id)
        return _setting_to_dict(s)


def delete_setting(profile_name: str, setting_id: int) -> None:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        ffi.DRS_DeleteProfileSetting(session, handle, setting_id)


def delete_base_setting(setting_id: int) -> None:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_GetBaseProfile(session)
        ffi.DRS_DeleteProfileSetting(session, handle, setting_id)


def create_profile(name: str) -> dict:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_CreateProfile(session, name)
        info = ffi.DRS_GetProfileInfo(session, handle)
        return {
            "profileName": info.profileName,
            "isPredefined": bool(info.isPredefined),
            "numOfApps": info.numOfApps,
            "numOfSettings": info.numOfSettings,
        }


def delete_profile(name: str) -> None:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_FindProfileByName(session, name)
        ffi.DRS_DeleteProfile(session, handle)


def list_apps(profile_name: str) -> list[dict]:
    _ensure_initialized()
    with drs_session() as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        return _get_all_apps(session, handle)


def add_app(profile_name: str, exe_name: str) -> None:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        ffi.DRS_CreateApplication(session, handle, exe_name)


def remove_app(profile_name: str, exe_name: str) -> None:
    _ensure_initialized()
    with drs_session(save_on_exit=True) as session:
        handle = ffi.DRS_FindProfileByName(session, profile_name)
        ffi.DRS_DeleteApplicationEx(session, handle, exe_name)


# ------------------------------------------------------------------
# Display control
# ------------------------------------------------------------------
def _get_primary_display_handle() -> ffi.NvDisplayHandle:
    handle = ffi.EnumNvidiaDisplayHandle(0)
    if handle is None:
        raise ffi.NvAPIError(-6, "EnumNvidiaDisplayHandle")  # NVIDIA_DEVICE_NOT_FOUND
    return handle


def _dvc_level_to_percent(level: int, info: ffi.NV_DVC_INFO) -> int:
    """Convert raw DVC level to 0-100 Digital Vibrance percentage.

    Maps: minLevel → 0%, 0 (default) → 50%, maxLevel → 100%.
    This matches NVIDIA Control Panel's Digital Vibrance scale.
    """
    if level >= 0 and info.maxLevel > 0:
        return 50 + round(level * 50 / info.maxLevel)
    elif level < 0 and info.minLevel < 0:
        return 50 - round(level * 50 / info.minLevel)
    return 50


def _percent_to_dvc_level(percent: int, info: ffi.NV_DVC_INFO) -> int:
    """Convert 0-100 Digital Vibrance percentage to raw DVC level.

    Maps: 0% → minLevel, 50% (default) → 0, 100% → maxLevel.
    This matches NVIDIA Control Panel's Digital Vibrance scale.
    """
    if percent >= 50:
        return round((percent - 50) * info.maxLevel / 50)
    elif info.minLevel < 0:
        return round((50 - percent) * info.minLevel / 50)
    return 0


def get_display_info() -> dict:
    _ensure_initialized()
    handle = _get_primary_display_handle()
    dvc = ffi.GetDVCInfo(handle)
    saturation = _dvc_level_to_percent(dvc.currentLevel, dvc)
    mode = ffi.GetCurrentDisplayMode()
    return {
        "width": mode["width"],
        "height": mode["height"],
        "refresh": mode["refresh"],
        "saturation": saturation,
    }


def set_saturation(level: int) -> dict:
    _ensure_initialized()
    handle = _get_primary_display_handle()
    dvc = ffi.GetDVCInfo(handle)
    raw = _percent_to_dvc_level(max(0, min(100, level)), dvc)
    ffi.SetDVCLevel(handle, raw)
    return get_display_info()


def set_resolution(
    width: int, height: int, refresh: int | None = None, stretch: bool | None = True
) -> dict:
    _ensure_initialized()
    if refresh is None:
        refresh = ffi.GetMaxRefreshForResolution(width, height)
        if refresh == 0:
            raise ffi.NvAPIError(-5, f"No display mode found for {width}x{height}")
    ffi.SetDisplayMode(width, height, refresh, stretch=stretch)
    return get_display_info()


def fix_refresh_rates(skip_devices: list[str] | None = None) -> list[dict]:
    """Set all active monitors to their max refresh rate for current resolution."""
    _ensure_initialized()
    skip = set(skip_devices or [])
    adapters = ffi.EnumDisplayAdapters()
    results = []
    for adapter in adapters:
        name = adapter["name"]
        if not adapter["active"] or name in skip:
            continue
        try:
            mode = ffi.GetCurrentDisplayModeForDevice(name)
            max_hz = ffi.GetMaxRefreshForDevice(name, mode["width"], mode["height"])
            changed = False
            if max_hz > mode["refresh"]:
                ffi.SetDeviceRefreshRate(name, max_hz)
                changed = True
            results.append({
                "device": name,
                "resolution": f"{mode['width']}x{mode['height']}",
                "refresh_before": mode["refresh"],
                "refresh_after": max_hz if changed else mode["refresh"],
                "changed": changed,
            })
        except ffi.NvAPIError:
            logger.warning("failed to fix refresh for %s", name)
    return results


def apply_gaming_preset(
    width: int,
    height: int,
    saturation: int = 90,
    refresh: int | None = None,
    stretch: bool = True,
    disable_monitor: bool = False,
    stop_glazewm: bool = False,
    fix_refresh: bool = False,
    skip_devices: list[str] | None = None,
) -> dict:
    _ensure_initialized()
    if stop_glazewm:
        _stop_glazewm()
    if disable_monitor:
        try:
            from . import setupapi
            pnp_id = setupapi.get_primary_monitor_pnpid()
            setupapi.disable_monitor_device(pnp_id)
        except Exception as e:
            logger.warning("monitor disable failed (non-fatal): %s", e)
    set_resolution(width, height, refresh, stretch=stretch)
    result = set_saturation(saturation)
    if fix_refresh:
        result["refresh_fixes"] = fix_refresh_rates(skip_devices)
    return result


def apply_desktop_preset(
    saturation: int = 50,
    enable_monitor: bool = False,
    start_glazewm: bool = False,
    fix_refresh: bool = False,
    skip_devices: list[str] | None = None,
) -> dict:
    _ensure_initialized()
    if enable_monitor:
        try:
            from . import setupapi
            pnp_id = setupapi.get_primary_monitor_pnpid()
            setupapi.enable_monitor_device(pnp_id)
        except Exception as e:
            logger.warning("monitor enable failed (non-fatal): %s", e)
    native = ffi.GetNativeDisplayMode()
    ffi.SetDisplayMode(
        native["width"], native["height"], native["refresh"], stretch=False
    )
    result = set_saturation(saturation)
    if fix_refresh:
        result["refresh_fixes"] = fix_refresh_rates(skip_devices)
    if start_glazewm:
        _start_glazewm()
    return result


# ------------------------------------------------------------------
# GlazeWM process management
# ------------------------------------------------------------------
def _stop_glazewm() -> None:
    """Kill glazewm.exe and store its path for later restart."""
    global _glazewm_path
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='glazewm.exe'", "get", "ExecutablePath"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line and line.lower().endswith(".exe"):
                _glazewm_path = line
                break
    except Exception:
        logger.warning("failed to query glazewm.exe path")

    try:
        subprocess.run(
            ["taskkill", "/IM", "glazewm.exe", "/F"],
            capture_output=True, timeout=5,
        )
    except Exception:
        logger.warning("failed to kill glazewm.exe")


def _start_glazewm() -> None:
    """Restart GlazeWM from the previously captured path."""
    global _glazewm_path
    if _glazewm_path is None:
        logger.info("no glazewm path stored, skipping restart")
        return
    try:
        subprocess.Popen(
            [_glazewm_path],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception:
        logger.warning("failed to start glazewm at %s", _glazewm_path)
