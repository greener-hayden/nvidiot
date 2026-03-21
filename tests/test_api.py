"""Test: API endpoints via stdlib http.client."""

import http.client
import json
import threading

import pytest

from main import TOKEN

# ---------------------------------------------------------------------------
# Server fixture — start once per session in a background thread
# ---------------------------------------------------------------------------
_server = None


@pytest.fixture(scope="session", autouse=True)
def api_server():
    global _server
    from api.server import NvidiotServer, Handler

    _server = NvidiotServer(("127.0.0.1", 18000), Handler)
    t = threading.Thread(target=_server.serve_until_stopped, daemon=True)
    t.start()
    yield _server
    _server._stop = True


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _request(method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", 18000, timeout=5)
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    payload = json.dumps(body).encode() if body is not None else None
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    status = resp.status
    raw = resp.read()
    conn.close()
    data = json.loads(raw) if raw else None
    return status, data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_get_gpus():
    status, data = _request("GET", "/gpu")
    assert status == 200
    assert isinstance(data, list)
    assert len(data) > 0
    assert "name" in data[0]


def test_get_base_profile():
    status, data = _request("GET", "/base")
    assert status == 200
    assert "settings" in data
    assert "profileName" in data


def test_list_profiles():
    status, data = _request("GET", "/profiles")
    assert status == 200
    assert isinstance(data, list)


def test_get_base_setting():
    status, data = _request("GET", "/base/settings/24")  # 0x18 = VSYNC_MODE
    assert status == 200
    assert "settingId" in data
    assert data["settingId"] == 24


def test_setting_ids():
    status, data = _request("GET", "/settings/ids")
    assert status == 200
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "name" in data[0]


def test_create_and_delete_profile():
    name = "__nvidiot_test_profile__"
    # Create
    status, data = _request("POST", "/profiles", {"name": name}, AUTH)
    assert status == 201
    assert data["profileName"] == name

    # Verify it exists
    status, data = _request("GET", f"/profiles/{name}")
    assert status == 200

    # Delete
    status, _ = _request("DELETE", f"/profiles/{name}", headers=AUTH)
    assert status == 204


def test_round_trip_setting():
    """PUT a base setting, GET it back, restore."""
    setting_id = 24  # VSYNC_MODE
    # Read original
    status, data = _request("GET", f"/base/settings/{setting_id}")
    assert status == 200
    original_value = data["currentValue"]

    new_value = 0 if original_value != 0 else 1

    # Write
    status, data = _request(
        "PUT", f"/base/settings/{setting_id}", {"value": new_value}, AUTH
    )
    assert status == 200
    assert data["currentValue"] == new_value

    # Restore
    status, data = _request(
        "PUT", f"/base/settings/{setting_id}", {"value": original_value}, AUTH
    )
    assert status == 200
    assert data["currentValue"] == original_value


def test_write_without_auth_returns_401():
    """Write endpoints require Bearer token."""
    status, _ = _request("POST", "/profiles", {"name": "should_fail"})
    assert status == 401


def test_invalid_resolution_returns_422():
    """Out-of-bounds display parameters are rejected."""
    status, _ = _request(
        "PUT", "/display/resolution", {"width": 1, "height": 1}, AUTH
    )
    assert status == 422
