"""SetupAPI ctypes bindings for enabling/disabling monitor devices."""

import ctypes
import ctypes.wintypes as wt
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
# GUID structure
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


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
DIGCF_PRESENT = 0x00000002
DIF_PROPERTYCHANGE = 0x00000012
DICS_ENABLE = 0x00000001
DICS_DISABLE = 0x00000002
DICS_FLAG_GLOBAL = 0x00000001

DISPLAY_DEVICE_ACTIVE = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004


# ------------------------------------------------------------------
# SetupAPI structures
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# DISPLAY_DEVICEW for EnumDisplayDevices
# ------------------------------------------------------------------
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


def get_primary_monitor_pnpid() -> str:
    """Return the PnP device ID of the primary monitor.

    Walks EnumDisplayDevices to find the primary adapter, then its
    child monitor, and returns the DeviceID (PnP hardware path).
    """
    # Find primary adapter
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

    # Find the monitor attached to the primary adapter
    monitor = DISPLAY_DEVICEW()
    monitor.cb = sizeof(DISPLAY_DEVICEW)
    if not _EnumDisplayDevicesW(primary_adapter_name, 0, byref(monitor), 0):
        raise SetupAPIError("no monitor found on primary adapter")

    device_id = monitor.DeviceID
    if not device_id:
        raise SetupAPIError("primary monitor has no DeviceID")

    return device_id


def _set_monitor_state(pnp_id: str, enable: bool) -> None:
    """Enable or disable a monitor device in Device Manager by PnP ID."""
    # Extract the hardware ID portion for matching.
    # EnumDisplayDevices returns e.g. "MONITOR\\MSI3EA5\\{guid}\\0008"
    # SetupAPI instance IDs look like  "DISPLAY\\MSI3EA5\\5&xxx&1&UIDnnn"
    # We match on the model ID (second segment) since the first segment differs.
    parts = pnp_id.replace("\\\\", "\\").split("\\")
    if len(parts) >= 2:
        model_id = parts[1].upper()
    else:
        model_id = pnp_id.upper()

    # Use DIGCF_PRESENT when disabling (targets the active instance),
    # but enumerate all devices when enabling (disabled devices aren't "present").
    flags = DIGCF_PRESENT if not enable else 0
    dev_info = _SetupDiGetClassDevsW(
        byref(GUID_DEVCLASS_MONITOR), None, None, flags,
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

            # Get the device instance ID
            buf = ctypes.create_unicode_buffer(512)
            needed = wt.DWORD(0)
            if not _SetupDiGetDeviceInstanceIdW(
                dev_info, byref(dev_data), buf, 512, byref(needed)
            ):
                continue

            # Instance IDs look like "DISPLAY\MSI3EA5\5&xxx&1&UIDnnn"
            # Match on the model ID segment (e.g. "MSI3EA5")
            instance_id = buf.value.upper()
            id_parts = instance_id.split("\\")
            if len(id_parts) >= 2 and id_parts[1] == model_id:
                pass  # match — fall through to state change
            else:
                continue

            # Found the matching monitor — change its state
            params = SP_PROPCHANGE_PARAMS()
            params.ClassInstallHeader.cbSize = sizeof(SP_CLASSINSTALL_HEADER)
            params.ClassInstallHeader.InstallFunction = DIF_PROPERTYCHANGE
            params.StateChange = DICS_ENABLE if enable else DICS_DISABLE
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
                action = "enable" if enable else "disable"
                raise SetupAPIError(
                    f"SetupDiCallClassInstaller failed to {action} monitor "
                    f"(requires admin privileges)"
                )
            return

        raise SetupAPIError(
            f"no monitor device matching model '{model_id}' found in Device Manager"
        )
    finally:
        _SetupDiDestroyDeviceInfoList(dev_info)


def disable_monitor_device(pnp_id: str) -> None:
    """Disable a monitor device in Device Manager (requires admin)."""
    _set_monitor_state(pnp_id, enable=False)


def enable_monitor_device(pnp_id: str) -> None:
    """Enable a monitor device in Device Manager (requires admin)."""
    _set_monitor_state(pnp_id, enable=True)
