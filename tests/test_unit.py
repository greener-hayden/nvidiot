"""Unit tests — no NVIDIA hardware required.

Tests value transformations, validation boundaries, and API contract
consistency using mocks instead of real GPU calls.
"""

import ctypes
import http.client
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.validate import (
    ValidationError,
    validate_app_request,
    validate_create_profile,
    validate_desktop_preset,
    validate_gaming_preset,
    validate_set_resolution,
    validate_set_saturation,
)

# ---------------------------------------------------------------------------
# Patch the DLL load so nvapi.ffi and nvapi.service can be imported
# without nvapi64.dll present.  Only nvapi64 is mocked; user32 etc.
# pass through to the real WinDLL.
# ---------------------------------------------------------------------------
_real_WinDLL = ctypes.WinDLL


def _mock_windll(name, **kw):
    if "nvapi64" in name.lower():
        m = MagicMock()
        m.nvapi_QueryInterface = MagicMock(return_value=0)
        return m
    return _real_WinDLL(name, **kw)


with patch("ctypes.WinDLL", side_effect=_mock_windll):
    from nvapi.constants import NvAPI_Status
    from nvapi.ffi import NvAPIError
    from nvapi.service import (
        _dvc_level_to_percent,
        _percent_to_dvc_level,
        _validate_setting_write,
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _dvc(min_level: int, max_level: int) -> SimpleNamespace:
    """Create a mock DVC info object with the given level range."""
    return SimpleNamespace(minLevel=min_level, maxLevel=max_level)


# ===================================================================
# A. Saturation conversion (piecewise linear, centred on 0)
#
# The mapping is:
#   minLevel  → 0%
#   0         → 50%   (neutral / default)
#   maxLevel  → 100%
#
# Typical NVIDIA range: minLevel=-180, maxLevel=180
# ===================================================================


class TestDvcLevelToPercent:
    """Test raw DVC level → 0-100 percentage conversion."""

    def test_zero_level_is_50(self):
        assert _dvc_level_to_percent(0, _dvc(-180, 180)) == 50

    def test_max_level_is_100(self):
        assert _dvc_level_to_percent(180, _dvc(-180, 180)) == 100

    def test_min_level_is_0(self):
        assert _dvc_level_to_percent(-180, _dvc(-180, 180)) == 0

    def test_positive_midpoint(self):
        # level=90 is halfway between 0 and 180 → 75%
        assert _dvc_level_to_percent(90, _dvc(-180, 180)) == 75

    def test_negative_midpoint(self):
        # level=-90 is halfway between -180 and 0 → 25%
        assert _dvc_level_to_percent(-90, _dvc(-180, 180)) == 25

    def test_zero_level_with_asymmetric_range(self):
        assert _dvc_level_to_percent(0, _dvc(-100, 200)) == 50

    def test_max_with_asymmetric_range(self):
        assert _dvc_level_to_percent(200, _dvc(-100, 200)) == 100

    def test_min_with_asymmetric_range(self):
        assert _dvc_level_to_percent(-100, _dvc(-100, 200)) == 0

    def test_zero_max_level_returns_50(self):
        # Edge case: maxLevel == 0, level >= 0 → falls through to return 50
        assert _dvc_level_to_percent(0, _dvc(-100, 0)) == 50

    def test_zero_min_level_positive_only(self):
        # minLevel == 0, maxLevel == 100, level=0 → 50
        assert _dvc_level_to_percent(0, _dvc(0, 100)) == 50

    def test_positive_level_zero_min(self):
        # minLevel == 0, maxLevel == 100, level=100 → 100
        assert _dvc_level_to_percent(100, _dvc(0, 100)) == 100


class TestPercentToDvcLevel:
    """Test 0-100 percentage → raw DVC level conversion."""

    def test_50_percent_gives_zero(self):
        assert _percent_to_dvc_level(50, _dvc(-180, 180)) == 0

    def test_100_percent_gives_max(self):
        assert _percent_to_dvc_level(100, _dvc(-180, 180)) == 180

    def test_0_percent_gives_min(self):
        assert _percent_to_dvc_level(0, _dvc(-180, 180)) == -180

    def test_75_percent(self):
        # 75% is halfway between 50% and 100% → level = 90
        assert _percent_to_dvc_level(75, _dvc(-180, 180)) == 90

    def test_25_percent(self):
        # 25% is halfway between 0% and 50% → level = -90
        assert _percent_to_dvc_level(25, _dvc(-180, 180)) == -90

    def test_0_percent_zero_min(self):
        # minLevel == 0 → 0% maps to 0 (not negative)
        assert _percent_to_dvc_level(0, _dvc(0, 100)) == 0

    def test_100_percent_asymmetric(self):
        assert _percent_to_dvc_level(100, _dvc(-100, 200)) == 200

    def test_0_percent_asymmetric(self):
        assert _percent_to_dvc_level(0, _dvc(-100, 200)) == -100


class TestSaturationRoundTrip:
    """Verify that percent → level → percent is identity for all 0-100."""

    @pytest.mark.parametrize("min_l,max_l", [
        (-180, 180),    # typical NVIDIA range
        (-100, 300),    # asymmetric
        (-100, 100),    # symmetric
    ])
    def test_round_trip_all_percents(self, min_l, max_l):
        info = _dvc(min_l, max_l)
        for pct in range(101):
            level = _percent_to_dvc_level(pct, info)
            back = _dvc_level_to_percent(level, info)
            assert back == pct, (
                f"Round-trip failed for {pct}% with range [{min_l}, {max_l}]: "
                f"level={level}, back={back}"
            )


# ===================================================================
# B. Service-level clamping
# ===================================================================


class TestSetSaturationClamping:
    def _call_set_saturation(self, level: int, min_l: int = -180, max_l: int = 180) -> int:
        """Call set_saturation with all FFI mocked, return the raw level
        that was passed to SetDVCLevel."""
        import nvapi.ffi as ffi_mod
        import nvapi.service as svc

        dvc_info = SimpleNamespace(minLevel=min_l, maxLevel=max_l, currentLevel=0)
        captured = {}

        with (
            patch.object(svc, "_ensure_initialized"),
            patch.object(svc, "_get_primary_display_handle", return_value="h"),
            patch.object(ffi_mod, "GetDVCInfo", return_value=dvc_info),
            patch.object(ffi_mod, "SetDVCLevel", side_effect=lambda h, v: captured.update(raw=v)),
            patch.object(svc, "get_display_info", return_value={"width": 1920, "height": 1080, "refresh": 60, "saturation": 50}),
        ):
            svc.set_saturation(level)

        return captured["raw"]

    def test_clamps_negative_to_zero(self):
        raw = self._call_set_saturation(-10)
        # level=-10 clamped to 0 → _percent_to_dvc_level(0) → minLevel
        assert raw == -180

    def test_clamps_above_100(self):
        raw = self._call_set_saturation(150)
        # level=150 clamped to 100 → _percent_to_dvc_level(100) → maxLevel
        assert raw == 180

    def test_passes_50_as_zero_raw(self):
        raw = self._call_set_saturation(50)
        # 50% → raw level 0 (neutral)
        assert raw == 0


# ===================================================================
# C. Validation functions (replaces Pydantic model tests)
# ===================================================================


class TestSetSaturationValidation:
    def test_valid_zero(self):
        d = validate_set_saturation({"level": 0})
        assert d["level"] == 0

    def test_valid_100(self):
        d = validate_set_saturation({"level": 100})
        assert d["level"] == 100

    def test_rejects_negative(self):
        with pytest.raises(ValidationError):
            validate_set_saturation({"level": -1})

    def test_rejects_101(self):
        with pytest.raises(ValidationError):
            validate_set_saturation({"level": 101})


class TestSetResolutionValidation:
    def test_valid_min_bounds(self):
        d = validate_set_resolution({"width": 640, "height": 480, "refresh": 24})
        assert d["width"] == 640
        assert d["height"] == 480
        assert d["refresh"] == 24

    def test_valid_max_bounds(self):
        d = validate_set_resolution({"width": 15360, "height": 8640, "refresh": 600})
        assert d["width"] == 15360

    def test_rejects_low_width(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 639, "height": 1080})

    def test_rejects_high_width(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 15361, "height": 1080})

    def test_rejects_low_height(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 1920, "height": 479})

    def test_rejects_high_height(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 1920, "height": 8641})

    def test_rejects_low_refresh(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 1920, "height": 1080, "refresh": 23})

    def test_rejects_high_refresh(self):
        with pytest.raises(ValidationError):
            validate_set_resolution({"width": 1920, "height": 1080, "refresh": 601})

    def test_refresh_optional_defaults_none(self):
        d = validate_set_resolution({"width": 1920, "height": 1080})
        assert d["refresh"] is None

    def test_stretch_defaults_true(self):
        d = validate_set_resolution({"width": 1920, "height": 1080})
        assert d["stretch"] is True


class TestPresetDefaults:
    def test_gaming_preset_defaults(self):
        d = validate_gaming_preset({"width": 1920, "height": 1080})
        assert d["saturation"] == 90
        assert d["stretch"] is True
        assert d["refresh"] is None

    def test_desktop_preset_defaults(self):
        d = validate_desktop_preset({})
        assert d["saturation"] == 50


class TestProfileAndAppValidation:
    def test_create_profile_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            validate_create_profile({"name": ""})

    def test_create_profile_accepts_valid_name(self):
        d = validate_create_profile({"name": "my_profile"})
        assert d["name"] == "my_profile"

    def test_app_request_rejects_empty_exe(self):
        with pytest.raises(ValidationError):
            validate_app_request({"exe": ""})

    def test_app_request_accepts_valid_exe(self):
        d = validate_app_request({"exe": "game.exe"})
        assert d["exe"] == "game.exe"


# ===================================================================
# D. DRS setting validation
# ===================================================================


class TestValidateSettingWrite:
    def test_rejects_unknown_setting_id(self):
        with pytest.raises(NvAPIError):
            _validate_setting_write(0xDEADBEEF, 0)

    def test_accepts_known_id_without_enum(self):
        # AA_MODE_REPLAY (0x1A) is in SETTING_IDS but not in SETTING_VALUE_RANGES
        _validate_setting_write(0x0000001A, 999)  # should not raise

    def test_vsync_accepts_valid_values(self):
        for v in (0, 1, 2):
            _validate_setting_write(0x00000018, v)

    def test_vsync_rejects_invalid(self):
        with pytest.raises(NvAPIError):
            _validate_setting_write(0x00000018, 5)

    def test_texture_quality_accepts_all(self):
        for v in range(4):
            _validate_setting_write(0x00001014, v)

    def test_texture_quality_rejects_invalid(self):
        with pytest.raises(NvAPIError):
            _validate_setting_write(0x00001014, 4)

    def test_pstate_accepts_all(self):
        for v in range(4):
            _validate_setting_write(0x0000002F, v)

    def test_pstate_rejects_invalid(self):
        with pytest.raises(NvAPIError):
            _validate_setting_write(0x0000002F, 99)


# ===================================================================
# E. API error mapping (via test server)
# ===================================================================


class TestAPIErrorMapping:
    @pytest.fixture(autouse=True)
    def _setup_server(self):
        """Start a test server with DLL mocked."""
        import api.server as srv_mod
        srv_mod._last_write = 0.0  # reset write cooldown

        with patch("ctypes.WinDLL", side_effect=_mock_windll):
            from api.server import NvidiotServer, Handler, init_token
            from main import TOKEN
            init_token(TOKEN)

        self.server = NvidiotServer(("127.0.0.1", 18001), Handler)
        t = threading.Thread(target=self.server.serve_until_stopped, daemon=True)
        t.start()
        self.auth = {"Authorization": f"Bearer {TOKEN}"}
        yield
        self.server._stop = True

    def _req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", 18001, timeout=5)
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        payload = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=payload, headers=hdrs)
        resp = conn.getresponse()
        status = resp.status
        raw = resp.read()
        conn.close()
        return status, json.loads(raw) if raw else None

    def test_display_returns_shape(self):
        mock_data = {"width": 1920, "height": 1080, "refresh": 144, "saturation": 50}
        with patch("nvapi.service.get_display_info", return_value=mock_data):
            status, data = self._req("GET", "/display")
        assert status == 200
        assert data["width"] == 1920
        assert data["saturation"] == 50

    def test_saturation_forwards_level(self):
        mock_data = {"width": 1920, "height": 1080, "refresh": 144, "saturation": 75}
        with patch("nvapi.service.set_saturation", return_value=mock_data) as mock_set:
            status, data = self._req(
                "PUT", "/display/saturation", {"level": 75}, self.auth
            )
        assert status == 200
        mock_set.assert_called_once_with(75)

    def test_error_profile_not_found_404(self):
        err = NvAPIError(NvAPI_Status.NVAPI_PROFILE_NOT_FOUND, "get_profile")
        mock_fn = MagicMock(side_effect=err)
        mock_fn.__name__ = "get_profile"
        with patch("nvapi.service.get_profile", mock_fn):
            status, _ = self._req("GET", "/profiles/nonexistent")
        assert status == 404

    def test_error_invalid_argument_400(self):
        err = NvAPIError(NvAPI_Status.NVAPI_INVALID_ARGUMENT, "get_profile")
        mock_fn = MagicMock(side_effect=err)
        mock_fn.__name__ = "get_profile"
        with patch("nvapi.service.get_profile", mock_fn):
            status, _ = self._req("GET", "/profiles/bad")
        assert status == 400

    def test_error_name_in_use_409(self):
        err = NvAPIError(NvAPI_Status.NVAPI_PROFILE_NAME_IN_USE, "create_profile")
        mock_fn = MagicMock(side_effect=err)
        mock_fn.__name__ = "create_profile"
        with patch("nvapi.service.create_profile", mock_fn):
            status, _ = self._req("POST", "/profiles", {"name": "dup"}, self.auth)
        assert status == 409

    def test_error_unknown_maps_to_500(self):
        err = NvAPIError(NvAPI_Status.NVAPI_ERROR, "get_display_info")
        mock_fn = MagicMock(side_effect=err)
        mock_fn.__name__ = "get_display_info"
        with patch("nvapi.service.get_display_info", mock_fn):
            status, _ = self._req("GET", "/display")
        assert status == 500
