"""Test: load nvapi64.dll and initialize."""

import pytest

from nvapi.constants import NvAPI_Status


def test_load_and_initialize():
    from nvapi import ffi

    status = ffi.Initialize()
    assert status == NvAPI_Status.NVAPI_OK


def test_get_error_message():
    from nvapi import ffi

    ffi.Initialize()
    msg = ffi.GetErrorMessage(NvAPI_Status.NVAPI_OK)
    assert isinstance(msg, str)
