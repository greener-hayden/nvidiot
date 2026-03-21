"""Test: service-layer operations."""

import pytest

from nvapi import ffi, service
from nvapi.constants import SETTING_NAMES_TO_IDS


@pytest.fixture(autouse=True)
def init_nvapi():
    ffi.Initialize()


def test_list_gpus():
    gpus = service.list_gpus()
    assert len(gpus) > 0
    assert "name" in gpus[0]


def test_list_profiles():
    profiles = service.list_profiles()
    assert isinstance(profiles, list)
    assert len(profiles) > 0


def test_get_base_profile():
    base = service.get_base_profile()
    assert "settings" in base
    assert len(base["settings"]) > 0


def test_read_write_restore_setting():
    """Round-trip: read a setting, write a new value, verify, restore."""
    vsync_id = SETTING_NAMES_TO_IDS["VSYNC_MODE"]
    original = service.get_base_setting(vsync_id)
    original_value = original["currentValue"]

    # Write a different value (toggle between 0 and 1)
    new_value = 0 if original_value != 0 else 1
    updated = service.set_base_setting(vsync_id, new_value)
    assert updated["currentValue"] == new_value

    # Restore
    service.set_base_setting(vsync_id, original_value)
    restored = service.get_base_setting(vsync_id)
    assert restored["currentValue"] == original_value
