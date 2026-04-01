"""SetupAPI ctypes bindings for enabling/disabling monitor devices."""

import ctypes
import ctypes.wintypes as wt
import subprocess
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_ubyte,
    c_uint32,
    c_ushort,
    c_wchar,
    sizeof,
)


# ------------------------------------------------------------------
# DLL loads
# ------------------------------------------------------------------
_setupapi = WinDLL("setupapi")
_user32 = WinDLL("user32")


# ------------------------------------------------------------------
# GUID / constants / structures
# ------------------------------------------------------------------
class GUID(Structure):
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


# Monitor class GUID: {4d36e96e-e325-11ce-bfc1-08002be10318}
GUID_DEVCLASS_MONITOR = GUID(
    0x4D36E96E, 0xE325, 0x11CE,
    (c_ubyte * 8)(0xBF, 0xC1, 0x08, 0x00, 0x2B, 0xE1, 0x03, 0x18),
)

DIGCF_PRESENT = 0x00000002
DIF_PROPERTYCHANGE = 0x00000012
DICS_DISABLE = 0x00000002
DICS_FLAG_GLOBAL = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004


class SP_DEVINFO_DATA(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wt.DWORD),
        ("Reserved", POINTER(c_uint32)),
    ]


class SP_CLASSINSTALL_HEADER(Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("InstallFunction", c_uint32),
    ]


class SP_PROPCHANGE_PARAMS(Structure):
    _fields_ = [
        ("ClassInstallHeader", SP_CLASSINSTALL_HEADER),
        ("StateChange", wt.DWORD),
        ("Scope", wt.DWORD),
        ("HwProfile", wt.DWORD),
    ]


class DISPLAY_DEVICEW(Structure):
    _fields_ = [
        ("cb", wt.DWORD),
        ("DeviceName", c_wchar * 32),
        ("DeviceString", c_wchar * 128),
        ("StateFlags", wt.DWORD),
        ("DeviceID", c_wchar * 128),
        ("DeviceKey", c_wchar * 128),
    ]


# ------------------------------------------------------------------
# SetupAPI function prototypes
# ------------------------------------------------------------------
_SetupDiGetClassDevsW = _setupapi.SetupDiGetClassDevsW
_SetupDiGetClassDevsW.restype = wt.HANDLE
_SetupDiGetClassDevsW.argtypes = [POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]

_SetupDiEnumDeviceInfo = _setupapi.SetupDiEnumDeviceInfo
_SetupDiEnumDeviceInfo.restype = wt.BOOL
_SetupDiEnumDeviceInfo.argtypes = [wt.HANDLE, wt.DWORD, POINTER(SP_DEVINFO_DATA)]

_SetupDiSetClassInstallParamsW = _setupapi.SetupDiSetClassInstallParamsW
_SetupDiSetClassInstallParamsW.restype = wt.BOOL
_SetupDiSetClassInstallParamsW.argtypes = [
    wt.HANDLE, POINTER(SP_DEVINFO_DATA), POINTER(SP_CLASSINSTALL_HEADER), wt.DWORD,
]

_SetupDiCallClassInstaller = _setupapi.SetupDiCallClassInstaller
_SetupDiCallClassInstaller.restype = wt.BOOL
_SetupDiCallClassInstaller.argtypes = [wt.DWORD, wt.HANDLE, POINTER(SP_DEVINFO_DATA)]

_SetupDiDestroyDeviceInfoList = _setupapi.SetupDiDestroyDeviceInfoList
_SetupDiDestroyDeviceInfoList.restype = wt.BOOL
_SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]

_SetupDiGetDeviceInstanceIdW = _setupapi.SetupDiGetDeviceInstanceIdW
_SetupDiGetDeviceInstanceIdW.restype = wt.BOOL
_SetupDiGetDeviceInstanceIdW.argtypes = [
    wt.HANDLE, POINTER(SP_DEVINFO_DATA), wt.LPWSTR, wt.DWORD, POINTER(wt.DWORD),
]

_EnumDisplayDevicesW = _user32.EnumDisplayDevicesW
_EnumDisplayDevicesW.restype = wt.BOOL
_EnumDisplayDevicesW.argtypes = [wt.LPCWSTR, wt.DWORD, POINTER(DISPLAY_DEVICEW), wt.DWORD]

INVALID_HANDLE_VALUE = wt.HANDLE(-1).value


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

class SetupAPIError(Exception):
    """Raised when a SetupAPI operation fails."""
    pass


# Cached so lookups survive the monitor being disabled (a disabled
# monitor disappears from EnumDisplayDevices).
_cached_primary_pnpid: str | None = None
_cached_instance_id: str | None = None


def get_primary_monitor_pnpid() -> str:
    """Return the PnP device ID of the primary monitor (cached)."""
    global _cached_primary_pnpid
    if _cached_primary_pnpid is not None:
        return _cached_primary_pnpid

    adapter = DISPLAY_DEVICEW()
    adapter.cb = sizeof(DISPLAY_DEVICEW)
    idx = 0
    primary_adapter_name = None
    while _EnumDisplayDevicesW(None, idx, byref(adapter), 0):
        if adapter.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE:
            primary_adapter_name = adapter.DeviceName
            break
        idx += 1

    if primary_adapter_name is None:
        raise SetupAPIError("no primary display adapter found")

    monitor = DISPLAY_DEVICEW()
    monitor.cb = sizeof(DISPLAY_DEVICEW)
    if not _EnumDisplayDevicesW(primary_adapter_name, 0, byref(monitor), 0):
        raise SetupAPIError("no monitor found on primary adapter")

    device_id = monitor.DeviceID
    if not device_id:
        raise SetupAPIError("primary monitor has no DeviceID")

    _cached_primary_pnpid = device_id
    return device_id


def _extract_model_id(pnp_id: str) -> str:
    """Extract model ID segment from an EnumDisplayDevices PnP path.

    E.g. "MONITOR\\MSI3EA5\\{guid}\\0008" → "MSI3EA5"
    """
    parts = pnp_id.replace("\\\\", "\\").split("\\")
    return parts[1].upper() if len(parts) >= 2 else pnp_id.upper()


def _enum_monitor_devices():
    """Yield (dev_info_handle, SP_DEVINFO_DATA, instance_id) for present monitors.

    Caller must NOT destroy the handle — it's destroyed when the generator
    is closed or exhausted.
    """
    dev_info = _SetupDiGetClassDevsW(
        byref(GUID_DEVCLASS_MONITOR), None, None, DIGCF_PRESENT,
    )
    if dev_info == INVALID_HANDLE_VALUE:
        raise SetupAPIError("SetupDiGetClassDevs failed")

    try:
        idx = 0
        while True:
            dev_data = SP_DEVINFO_DATA()
            dev_data.cbSize = sizeof(SP_DEVINFO_DATA)
            if not _SetupDiEnumDeviceInfo(dev_info, idx, byref(dev_data)):
                break
            idx += 1

            buf = ctypes.create_unicode_buffer(512)
            needed = wt.DWORD(0)
            if not _SetupDiGetDeviceInstanceIdW(
                dev_info, byref(dev_data), buf, 512, byref(needed)
            ):
                continue

            yield dev_info, dev_data, buf.value
    finally:
        _SetupDiDestroyDeviceInfoList(dev_info)


def disable_monitor_device(pnp_id: str) -> None:
    """Disable a monitor device in Device Manager (requires admin)."""
    global _cached_instance_id
    model_id = _extract_model_id(pnp_id)

    for dev_info, dev_data, instance_id in _enum_monitor_devices():
        id_parts = instance_id.upper().split("\\")
        if len(id_parts) < 2 or id_parts[1] != model_id:
            continue

        params = SP_PROPCHANGE_PARAMS()
        params.ClassInstallHeader.cbSize = sizeof(SP_CLASSINSTALL_HEADER)
        params.ClassInstallHeader.InstallFunction = DIF_PROPERTYCHANGE
        params.StateChange = DICS_DISABLE
        params.Scope = DICS_FLAG_GLOBAL
        params.HwProfile = 0

        if not _SetupDiSetClassInstallParamsW(
            dev_info,
            byref(dev_data),
            byref(params.ClassInstallHeader),
            sizeof(params),
        ):
            raise SetupAPIError("SetupDiSetClassInstallParams failed")

        if not _SetupDiCallClassInstaller(
            DIF_PROPERTYCHANGE, dev_info, byref(dev_data),
        ):
            err = ctypes.get_last_error() or ctypes.GetLastError()
            raise SetupAPIError(
                f"SetupDiCallClassInstaller failed to disable monitor "
                f"(error {err}, requires admin privileges)"
            )
        _cached_instance_id = instance_id
        return

    raise SetupAPIError(
        f"no monitor device matching model '{model_id}' found in Device Manager"
    )


def enable_monitor_device(pnp_id: str) -> None:
    """Enable a monitor device in Device Manager (requires admin).

    Uses pnputil because SetupAPI DICS_ENABLE does not reliably
    re-enable devices even with admin privileges.
    """
    global _cached_instance_id
    instance_id = _cached_instance_id
    if instance_id is None:
        instance_id = _find_instance_id(pnp_id)
    result = subprocess.run(
        ["pnputil", "/enable-device", instance_id],
        capture_output=True, text=True, timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise SetupAPIError(
            f"pnputil /enable-device failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    _cached_instance_id = None


def _find_instance_id(pnp_id: str) -> str:
    """Resolve an EnumDisplayDevices PnP ID to a SetupAPI instance ID."""
    model_id = _extract_model_id(pnp_id)
    for _, _, instance_id in _enum_monitor_devices():
        id_parts = instance_id.upper().split("\\")
        if len(id_parts) >= 2 and id_parts[1] == model_id:
            return instance_id
    raise SetupAPIError(
        f"no monitor device matching model '{model_id}' found in Device Manager"
    )
