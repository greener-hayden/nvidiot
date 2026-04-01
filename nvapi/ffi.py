"""Raw ctypes bindings to nvapi64.dll via QueryInterface."""

import ctypes
import ctypes.wintypes as wt
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_int,
    c_uint,
    c_uint32,
    c_wchar,
    c_wchar_p,
    pointer,
    sizeof,
)
from typing import Any

from .constants import NVAPI_FUNC_IDS, NvAPI_Status

# ------------------------------------------------------------------
# DLL load
# ------------------------------------------------------------------
try:
    _nvapi = WinDLL("nvapi64.dll")
except OSError as exc:
    raise RuntimeError(
        "Could not load nvapi64.dll — is an NVIDIA GPU driver installed?"
    ) from exc

_QueryInterface = _nvapi.nvapi_QueryInterface
_QueryInterface.restype = ctypes.c_void_p
_QueryInterface.argtypes = [c_uint]

# ------------------------------------------------------------------
# Helper: resolve a function pointer by ID
# ------------------------------------------------------------------
_cache: dict[int, Any] = {}


def _query(fn_id: int, restype: Any, argtypes: list[Any]) -> Any:
    if fn_id in _cache:
        return _cache[fn_id]
    ptr = _QueryInterface(fn_id)
    if not ptr:
        raise RuntimeError(f"nvapi_QueryInterface returned NULL for 0x{fn_id:08X}")
    proto = ctypes.CFUNCTYPE(restype, *argtypes)
    fn = proto(ptr)
    _cache[fn_id] = fn
    return fn


# ------------------------------------------------------------------
# Handles and types
# ------------------------------------------------------------------
NvDRSSessionHandle = ctypes.c_void_p
NvDRSProfileHandle = ctypes.c_void_p
NvPhysicalGpuHandle = ctypes.c_void_p

NVAPI_MAX_PHYSICAL_GPUS = 64
NVAPI_SHORT_STRING_MAX = 64
NVAPI_UNICODE_STRING_MAX = 2048
NVDRS_PROFILE_NAME_LEN = 2048
NVDRS_APP_NAME_LEN = 2048


# ------------------------------------------------------------------
# Structures
# ------------------------------------------------------------------
class NVDRS_PROFILE(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("profileName", c_wchar * NVDRS_PROFILE_NAME_LEN),
        ("gpuSupport", c_uint32 * 4),
        ("isPredefined", c_uint32),
        ("numOfApps", c_uint32),
        ("numOfSettings", c_uint32),
    ]


NVDRS_PROFILE_VER = sizeof(NVDRS_PROFILE) | (1 << 16)


class _SettingValue(ctypes.Union):
    _fields_ = [
        ("dwordValue", c_uint32),
        ("binaryValue", ctypes.c_ubyte * 4096),
        ("wszValue", c_wchar * NVAPI_UNICODE_STRING_MAX),
    ]


class NVDRS_SETTING(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("settingName", c_wchar * NVAPI_UNICODE_STRING_MAX),
        ("settingId", c_uint32),
        ("settingType", c_uint32),
        ("settingLocation", c_uint32),
        ("isCurrentPredefined", c_uint32),
        ("isPredefinedValid", c_uint32),
        ("predefinedValue", _SettingValue),
        ("currentValue", _SettingValue),
    ]


NVDRS_SETTING_VER = sizeof(NVDRS_SETTING) | (1 << 16)


class NVDRS_APPLICATION(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("isPredefined", c_uint32),
        ("appName", c_wchar * NVDRS_APP_NAME_LEN),
        ("userFriendlyName", c_wchar * NVDRS_APP_NAME_LEN),
        ("launcher", c_wchar * NVDRS_APP_NAME_LEN),
        ("fileInFolder", c_wchar * NVDRS_APP_NAME_LEN),
        ("isMetro", c_uint32),
        ("isCommandLine", c_uint32),
    ]


NVDRS_APPLICATION_VER = sizeof(NVDRS_APPLICATION) | (3 << 16)

NVAPI_THERMAL_TARGET_GPU = 1


class NV_GPU_THERMAL_SENSOR(Structure):
    _fields_ = [
        ("controller", c_int),
        ("defaultMinTemp", c_int),
        ("defaultMaxTemp", c_int),
        ("currentTemp", c_int),
        ("target", c_int),
    ]


class NV_GPU_THERMAL_SETTINGS(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("count", c_uint32),
        ("sensor", NV_GPU_THERMAL_SENSOR * 3),
    ]


NV_GPU_THERMAL_SETTINGS_VER = sizeof(NV_GPU_THERMAL_SETTINGS) | (2 << 16)

NvDisplayHandle = ctypes.c_void_p


class NV_DVC_INFO_V1(Structure):
    _fields_ = [
        ("version", c_uint32),
        ("currentLevel", c_int),
        ("minLevel", c_int),
        ("maxLevel", c_int),
    ]


NV_DVC_INFO_VER1 = sizeof(NV_DVC_INFO_V1) | (1 << 16)
NV_DVC_INFO = NV_DVC_INFO_V1
NV_DVC_INFO_VER = NV_DVC_INFO_VER1



# ------------------------------------------------------------------
# Win32 display mode structs (for resolution/refresh rate control)
# ------------------------------------------------------------------
class DEVMODEW(Structure):
    _fields_ = [
        ("dmDeviceName", c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", wt.DWORD),
        ("dmPositionX", c_int),
        ("dmPositionY", c_int),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", wt.DWORD),
        ("dmPelsWidth", wt.DWORD),
        ("dmPelsHeight", wt.DWORD),
        ("dmDisplayFlags", wt.DWORD),
        ("dmDisplayFrequency", wt.DWORD),
        ("dmICMMethod", wt.DWORD),
        ("dmICMIntent", wt.DWORD),
        ("dmMediaType", wt.DWORD),
        ("dmDitherType", wt.DWORD),
        ("dmReserved1", wt.DWORD),
        ("dmReserved2", wt.DWORD),
        ("dmPanningWidth", wt.DWORD),
        ("dmPanningHeight", wt.DWORD),
    ]


DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
DM_DISPLAYFIXEDOUTPUT = 0x20000000
DMDFO_DEFAULT = 0
DMDFO_STRETCH = 1
DMDFO_CENTER = 2
ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY = 0x00000001
DISP_CHANGE_SUCCESSFUL = 0


# ------------------------------------------------------------------
# Resolved function wrappers
# ------------------------------------------------------------------
def _id(name: str) -> int:
    return NVAPI_FUNC_IDS[name]


NvAPI_Status_t = c_int


def Initialize() -> int:
    fn = _query(_id("NvAPI_Initialize"), NvAPI_Status_t, [])
    return fn()


def Unload() -> int:
    fn = _query(_id("NvAPI_Unload"), NvAPI_Status_t, [])
    return fn()


def GetErrorMessage(status: int) -> str:
    fn = _query(
        _id("NvAPI_GetErrorMessage"),
        NvAPI_Status_t,
        [c_int, ctypes.c_char_p],
    )
    buf = ctypes.create_string_buffer(NVAPI_SHORT_STRING_MAX)
    fn(status, buf)
    return buf.value.decode("ascii", errors="replace")


def EnumPhysicalGPUs() -> list[NvPhysicalGpuHandle]:
    fn = _query(
        _id("NvAPI_EnumPhysicalGPUs"),
        NvAPI_Status_t,
        [POINTER(NvPhysicalGpuHandle * NVAPI_MAX_PHYSICAL_GPUS), POINTER(c_uint32)],
    )
    handles = (NvPhysicalGpuHandle * NVAPI_MAX_PHYSICAL_GPUS)()
    count = c_uint32()
    status = fn(byref(handles), byref(count))
    _check(status, "EnumPhysicalGPUs")
    safe_count = min(count.value, NVAPI_MAX_PHYSICAL_GPUS)
    return list(handles[:safe_count])


def GPU_GetFullName(handle: NvPhysicalGpuHandle) -> str:
    fn = _query(
        _id("NvAPI_GPU_GetFullName"),
        NvAPI_Status_t,
        [NvPhysicalGpuHandle, ctypes.c_char_p],
    )
    buf = ctypes.create_string_buffer(NVAPI_SHORT_STRING_MAX)
    status = fn(handle, buf)
    _check(status, "GPU_GetFullName")
    return buf.value.decode("ascii", errors="replace")


def GPU_GetThermalSettings(
    handle: NvPhysicalGpuHandle,
) -> NV_GPU_THERMAL_SETTINGS:
    fn = _query(
        _id("NvAPI_GPU_GetThermalSettings"),
        NvAPI_Status_t,
        [NvPhysicalGpuHandle, c_int, POINTER(NV_GPU_THERMAL_SETTINGS)],
    )
    settings = NV_GPU_THERMAL_SETTINGS()
    settings.version = NV_GPU_THERMAL_SETTINGS_VER
    status = fn(handle, NVAPI_THERMAL_TARGET_GPU, byref(settings))
    _check(status, "GPU_GetThermalSettings")
    return settings


# ------------------------------------------------------------------
# DRS functions
# ------------------------------------------------------------------
def DRS_CreateSession() -> NvDRSSessionHandle:
    fn = _query(
        _id("NvAPI_DRS_CreateSession"),
        NvAPI_Status_t,
        [POINTER(NvDRSSessionHandle)],
    )
    handle = NvDRSSessionHandle()
    status = fn(byref(handle))
    _check(status, "DRS_CreateSession")
    return handle


def DRS_DestroySession(session: NvDRSSessionHandle) -> None:
    fn = _query(
        _id("NvAPI_DRS_DestroySession"), NvAPI_Status_t, [NvDRSSessionHandle]
    )
    status = fn(session)
    _check(status, "DRS_DestroySession")


def DRS_LoadSettings(session: NvDRSSessionHandle) -> None:
    fn = _query(
        _id("NvAPI_DRS_LoadSettings"), NvAPI_Status_t, [NvDRSSessionHandle]
    )
    status = fn(session)
    _check(status, "DRS_LoadSettings")


def DRS_SaveSettings(session: NvDRSSessionHandle) -> None:
    fn = _query(
        _id("NvAPI_DRS_SaveSettings"), NvAPI_Status_t, [NvDRSSessionHandle]
    )
    status = fn(session)
    _check(status, "DRS_SaveSettings")


def DRS_GetBaseProfile(session: NvDRSSessionHandle) -> NvDRSProfileHandle:
    fn = _query(
        _id("NvAPI_DRS_GetBaseProfile"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, POINTER(NvDRSProfileHandle)],
    )
    profile = NvDRSProfileHandle()
    status = fn(session, byref(profile))
    _check(status, "DRS_GetBaseProfile")
    return profile


def DRS_GetNumProfiles(session: NvDRSSessionHandle) -> int:
    fn = _query(
        _id("NvAPI_DRS_GetNumProfiles"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, POINTER(c_uint32)],
    )
    count = c_uint32()
    status = fn(session, byref(count))
    _check(status, "DRS_GetNumProfiles")
    return count.value


def DRS_EnumProfiles(session: NvDRSSessionHandle, index: int) -> NvDRSProfileHandle:
    fn = _query(
        _id("NvAPI_DRS_EnumProfiles"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, c_uint32, POINTER(NvDRSProfileHandle)],
    )
    profile = NvDRSProfileHandle()
    status = fn(session, index, byref(profile))
    _check(status, "DRS_EnumProfiles")
    return profile


def DRS_GetProfileInfo(
    session: NvDRSSessionHandle, profile: NvDRSProfileHandle
) -> NVDRS_PROFILE:
    fn = _query(
        _id("NvAPI_DRS_GetProfileInfo"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_PROFILE)],
    )
    info = NVDRS_PROFILE()
    info.version = NVDRS_PROFILE_VER
    status = fn(session, profile, byref(info))
    _check(status, "DRS_GetProfileInfo")
    return info


def DRS_FindProfileByName(
    session: NvDRSSessionHandle, name: str
) -> NvDRSProfileHandle:
    fn = _query(
        _id("NvAPI_DRS_FindProfileByName"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, c_wchar_p, POINTER(NvDRSProfileHandle)],
    )
    profile = NvDRSProfileHandle()
    status = fn(session, name, byref(profile))
    _check(status, "DRS_FindProfileByName")
    return profile


def DRS_CreateProfile(
    session: NvDRSSessionHandle, name: str
) -> NvDRSProfileHandle:
    fn = _query(
        _id("NvAPI_DRS_CreateProfile"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, POINTER(NVDRS_PROFILE), POINTER(NvDRSProfileHandle)],
    )
    info = NVDRS_PROFILE()
    info.version = NVDRS_PROFILE_VER
    info.profileName = name
    profile = NvDRSProfileHandle()
    status = fn(session, byref(info), byref(profile))
    _check(status, "DRS_CreateProfile")
    return profile


def DRS_DeleteProfile(
    session: NvDRSSessionHandle, profile: NvDRSProfileHandle
) -> None:
    fn = _query(
        _id("NvAPI_DRS_DeleteProfile"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle],
    )
    status = fn(session, profile)
    _check(status, "DRS_DeleteProfile")


def DRS_GetSetting(
    session: NvDRSSessionHandle, profile: NvDRSProfileHandle, setting_id: int
) -> NVDRS_SETTING:
    fn = _query(
        _id("NvAPI_DRS_GetSetting"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32, POINTER(NVDRS_SETTING)],
    )
    setting = NVDRS_SETTING()
    setting.version = NVDRS_SETTING_VER
    status = fn(session, profile, setting_id, byref(setting))
    _check(status, "DRS_GetSetting")
    return setting


def DRS_SetSetting(
    session: NvDRSSessionHandle,
    profile: NvDRSProfileHandle,
    setting: NVDRS_SETTING,
) -> None:
    fn = _query(
        _id("NvAPI_DRS_SetSetting"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_SETTING)],
    )
    status = fn(session, profile, byref(setting))
    _check(status, "DRS_SetSetting")


def DRS_DeleteProfileSetting(
    session: NvDRSSessionHandle,
    profile: NvDRSProfileHandle,
    setting_id: int,
) -> None:
    fn = _query(
        _id("NvAPI_DRS_DeleteProfileSetting"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32],
    )
    status = fn(session, profile, setting_id)
    _check(status, "DRS_DeleteProfileSetting")


def DRS_EnumSettings(
    session: NvDRSSessionHandle, profile: NvDRSProfileHandle, start_index: int
) -> NVDRS_SETTING | None:
    fn = _query(
        _id("NvAPI_DRS_EnumSettings"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32, POINTER(c_uint32), POINTER(NVDRS_SETTING)],
    )
    setting = NVDRS_SETTING()
    setting.version = NVDRS_SETTING_VER
    count = c_uint32(1)
    status = fn(session, profile, start_index, byref(count), byref(setting))
    if status == NvAPI_Status.NVAPI_END_ENUMERATION:
        return None
    _check(status, "DRS_EnumSettings")
    return setting


def DRS_EnumApplications(
    session: NvDRSSessionHandle, profile: NvDRSProfileHandle, start_index: int
) -> NVDRS_APPLICATION | None:
    fn = _query(
        _id("NvAPI_DRS_EnumApplications"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, c_uint32, POINTER(c_uint32), POINTER(NVDRS_APPLICATION)],
    )
    app = NVDRS_APPLICATION()
    app.version = NVDRS_APPLICATION_VER
    count = c_uint32(1)
    status = fn(session, profile, start_index, byref(count), byref(app))
    if status == NvAPI_Status.NVAPI_END_ENUMERATION:
        return None
    _check(status, "DRS_EnumApplications")
    return app


def DRS_CreateApplication(
    session: NvDRSSessionHandle,
    profile: NvDRSProfileHandle,
    app_name: str,
) -> None:
    fn = _query(
        _id("NvAPI_DRS_CreateApplication"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_APPLICATION)],
    )
    app = NVDRS_APPLICATION()
    app.version = NVDRS_APPLICATION_VER
    app.appName = app_name
    status = fn(session, profile, byref(app))
    _check(status, "DRS_CreateApplication")


def DRS_DeleteApplicationEx(
    session: NvDRSSessionHandle,
    profile: NvDRSProfileHandle,
    app_name: str,
) -> None:
    fn = _query(
        _id("NvAPI_DRS_DeleteApplicationEx"),
        NvAPI_Status_t,
        [NvDRSSessionHandle, NvDRSProfileHandle, POINTER(NVDRS_APPLICATION)],
    )
    app = NVDRS_APPLICATION()
    app.version = NVDRS_APPLICATION_VER
    app.appName = app_name
    status = fn(session, profile, byref(app))
    _check(status, "DRS_DeleteApplicationEx")


# ------------------------------------------------------------------
# Display functions
# ------------------------------------------------------------------
def EnumNvidiaDisplayHandle(index: int) -> NvDisplayHandle:
    fn = _query(
        _id("NvAPI_EnumNvidiaDisplayHandle"),
        NvAPI_Status_t,
        [c_int, POINTER(NvDisplayHandle)],
    )
    handle = NvDisplayHandle()
    status = fn(index, byref(handle))
    if status == NvAPI_Status.NVAPI_END_ENUMERATION:
        return None
    _check(status, "EnumNvidiaDisplayHandle")
    return handle


def GetDVCInfo(handle: NvDisplayHandle) -> NV_DVC_INFO:
    fn = _query(
        _id("NvAPI_GetDVCInfo"),
        NvAPI_Status_t,
        [NvDisplayHandle, c_uint32, POINTER(NV_DVC_INFO)],
    )
    info = NV_DVC_INFO()
    info.version = NV_DVC_INFO_VER
    # outputId=0 means the default/primary output for this display
    status = fn(handle, 0, byref(info))
    _check(status, "GetDVCInfo")
    return info


def SetDVCLevel(handle: NvDisplayHandle, level: int) -> None:
    fn = _query(
        _id("NvAPI_SetDVCLevel"),
        NvAPI_Status_t,
        [NvDisplayHandle, c_uint32, c_int],
    )
    # outputId=0 means the default/primary output for this display
    status = fn(handle, 0, level)
    _check(status, "SetDVCLevel")


_user32 = ctypes.WinDLL("user32", use_last_error=True)


def GetCurrentDisplayMode() -> dict:
    """Get current display resolution and refresh rate via Win32."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    _user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, byref(dm))
    return {
        "width": dm.dmPelsWidth,
        "height": dm.dmPelsHeight,
        "refresh": dm.dmDisplayFrequency,
    }


def GetNativeDisplayMode() -> dict:
    """Get the monitor's native panel resolution via QueryDisplayConfig (EDID-based)."""
    QDC_ONLY_ACTIVE_PATHS = 0x00000002

    # Get buffer sizes
    num_paths = c_uint32(0)
    num_modes = c_uint32(0)
    _user32.GetDisplayConfigBufferSizes(QDC_ONLY_ACTIVE_PATHS, byref(num_paths), byref(num_modes))
    if num_paths.value == 0 or num_modes.value == 0:
        return GetCurrentDisplayMode()

    # Query active display config
    paths = (ctypes.c_ubyte * (72 * num_paths.value))()  # DISPLAYCONFIG_PATH_INFO = 72 bytes
    modes = (ctypes.c_ubyte * (64 * num_modes.value))()  # DISPLAYCONFIG_MODE_INFO = 64 bytes
    result = _user32.QueryDisplayConfig(
        QDC_ONLY_ACTIVE_PATHS, byref(num_paths), paths, byref(num_modes), modes, None
    )
    if result != 0:
        return GetCurrentDisplayMode()

    # Find the target mode (type=2) which has the panel's native active size
    native_w, native_h, native_hz = 0, 0, 0
    for i in range(num_modes.value):
        offset = i * 64
        info_type = int.from_bytes(modes[offset:offset + 4], "little")
        if info_type == 2:  # DISPLAYCONFIG_MODE_INFO_TYPE_TARGET
            # targetVideoSignalInfo starts at offset 16 in mode_info
            data_offset = offset + 16
            if data_offset + 32 > len(modes):
                continue  # skip malformed entry
            # pixelRate (8 bytes), hSync num/den (8), vSync num/den (8), activeSize cx/cy (8)
            vsync_num = int.from_bytes(modes[data_offset + 16:data_offset + 20], "little")
            vsync_den = int.from_bytes(modes[data_offset + 20:data_offset + 24], "little")
            active_cx = int.from_bytes(modes[data_offset + 24:data_offset + 28], "little")
            active_cy = int.from_bytes(modes[data_offset + 28:data_offset + 32], "little")
            native_w = active_cx
            native_h = active_cy
            native_hz = round(vsync_num / vsync_den) if vsync_den else 0
            break

    if native_w == 0:
        return GetCurrentDisplayMode()

    # Find the max refresh rate available for this native resolution
    max_hz = GetMaxRefreshForResolution(native_w, native_h)
    return {"width": native_w, "height": native_h, "refresh": max_hz or native_hz}


def GetMaxRefreshForResolution(width: int, height: int) -> int:
    """Find the max refresh rate available for a given resolution."""
    best_hz = 0
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    i = 0
    while _user32.EnumDisplaySettingsW(None, i, byref(dm)):
        if dm.dmPelsWidth == width and dm.dmPelsHeight == height:
            if dm.dmDisplayFrequency > best_hz:
                best_hz = dm.dmDisplayFrequency
        i += 1
    return best_hz


def SetDisplayMode(
    width: int, height: int, refresh: int, stretch: bool | None = None
) -> None:
    """Set display resolution, refresh rate, and optionally scaling mode via Win32."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    dm.dmPelsWidth = width
    dm.dmPelsHeight = height
    dm.dmDisplayFrequency = refresh
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
    if stretch is not None:
        dm.dmDisplayFixedOutput = DMDFO_STRETCH if stretch else DMDFO_DEFAULT
        dm.dmFields |= DM_DISPLAYFIXEDOUTPUT
    result = _user32.ChangeDisplaySettingsExW(None, byref(dm), None, CDS_UPDATEREGISTRY, None)
    if result != DISP_CHANGE_SUCCESSFUL:
        raise NvAPIError(result, f"ChangeDisplaySettings({width}x{height}@{refresh})")


# ------------------------------------------------------------------
# Multi-monitor display functions
# ------------------------------------------------------------------
_DISPLAY_DEVICE_ACTIVE = 0x00000001
_DISPLAY_DEVICE_PRIMARY = 0x00000004


class _DISPLAY_DEVICEW(Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("DeviceName", c_wchar * 32),
        ("DeviceString", c_wchar * 128),
        ("StateFlags", wt.DWORD),
        ("DeviceID", c_wchar * 128),
        ("DeviceKey", c_wchar * 128),
    ]


def EnumDisplayAdapters() -> list[dict]:
    """Enumerate all display adapters, returning name/active/primary for each."""
    adapters = []
    dd = _DISPLAY_DEVICEW()
    dd.cb = sizeof(_DISPLAY_DEVICEW)
    idx = 0
    while _user32.EnumDisplayDevicesW(None, idx, byref(dd), 0):
        adapters.append({
            "name": dd.DeviceName,
            "active": bool(dd.StateFlags & _DISPLAY_DEVICE_ACTIVE),
            "primary": bool(dd.StateFlags & _DISPLAY_DEVICE_PRIMARY),
        })
        dd = _DISPLAY_DEVICEW()
        dd.cb = sizeof(_DISPLAY_DEVICEW)
        idx += 1
    return adapters


def GetCurrentDisplayModeForDevice(device_name: str) -> dict:
    """Get current resolution and refresh rate for a specific display adapter."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    if not _user32.EnumDisplaySettingsW(c_wchar_p(device_name), ENUM_CURRENT_SETTINGS, byref(dm)):
        raise NvAPIError(-1, f"EnumDisplaySettingsW failed for {device_name}")
    return {
        "width": dm.dmPelsWidth,
        "height": dm.dmPelsHeight,
        "refresh": dm.dmDisplayFrequency,
    }


def GetMaxRefreshForDevice(device_name: str, width: int, height: int) -> int:
    """Find the max refresh rate available for a given resolution on a specific device."""
    best_hz = 0
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    i = 0
    while _user32.EnumDisplaySettingsW(c_wchar_p(device_name), i, byref(dm)):
        if dm.dmPelsWidth == width and dm.dmPelsHeight == height:
            if dm.dmDisplayFrequency > best_hz:
                best_hz = dm.dmDisplayFrequency
        i += 1
    return best_hz


def SetDeviceRefreshRate(device_name: str, refresh: int) -> None:
    """Set only the refresh rate for a specific display adapter (no resolution change)."""
    dm = DEVMODEW()
    dm.dmSize = sizeof(DEVMODEW)
    dm.dmDisplayFrequency = refresh
    dm.dmFields = DM_DISPLAYFREQUENCY
    result = _user32.ChangeDisplaySettingsExW(
        c_wchar_p(device_name), byref(dm), None, CDS_UPDATEREGISTRY, None
    )
    if result != DISP_CHANGE_SUCCESSFUL:
        raise NvAPIError(result, f"ChangeDisplaySettings({device_name}@{refresh})")


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------
class NvAPIError(Exception):
    def __init__(self, status: int, func_name: str):
        self.status = status
        self.func_name = func_name
        try:
            msg = GetErrorMessage(status)
        except Exception:
            msg = f"status {status}"
        super().__init__(f"{func_name} failed: {msg} ({status})")


def _check(status: int, func_name: str) -> None:
    if status != NvAPI_Status.NVAPI_OK:
        raise NvAPIError(status, func_name)
