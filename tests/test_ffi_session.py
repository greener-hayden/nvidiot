"""Test: DRS session lifecycle and base profile read."""

import pytest

from nvapi import ffi
from nvapi.constants import NvAPI_Status, SETTING_NAMES_TO_IDS


@pytest.fixture(autouse=True)
def init_nvapi():
    ffi.Initialize()


def test_create_destroy_session():
    session = ffi.DRS_CreateSession()
    assert session is not None
    ffi.DRS_LoadSettings(session)
    ffi.DRS_DestroySession(session)


def test_read_base_profile():
    session = ffi.DRS_CreateSession()
    ffi.DRS_LoadSettings(session)
    base = ffi.DRS_GetBaseProfile(session)
    info = ffi.DRS_GetProfileInfo(session, base)
    assert info.numOfSettings > 0
    ffi.DRS_DestroySession(session)


def test_read_vsync_setting():
    session = ffi.DRS_CreateSession()
    ffi.DRS_LoadSettings(session)
    base = ffi.DRS_GetBaseProfile(session)
    vsync_id = SETTING_NAMES_TO_IDS["VSYNC_MODE"]
    setting = ffi.DRS_GetSetting(session, base, vsync_id)
    assert setting.settingId == vsync_id
    ffi.DRS_DestroySession(session)
