"""Stdlib HTTP server — replaces FastAPI + uvicorn."""

import json
import logging
import secrets
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote

from nvapi import service
from nvapi.constants import SETTING_IDS, NvAPI_Status
from nvapi.ffi import NvAPIError
from nvapi.setupapi import SetupAPIError

from .validate import (
    ValidationError,
    validate_app_request,
    validate_create_profile,
    validate_desktop_preset,
    validate_gaming_preset,
    validate_set_resolution,
    validate_set_saturation,
    validate_set_setting,
)

logger = logging.getLogger("nvidiot")

# --- Auth state ---
_TOKEN: str = ""


def init_token(token: str) -> None:
    global _TOKEN
    _TOKEN = token


# --- Write throttle ---
_last_write = 0.0
_MIN_INTERVAL = 0.5

_ALLOWED_ORIGIN = "http://127.0.0.1:6124"
_MAX_BODY = 65536

_STATUS_TO_HTTP = {
    NvAPI_Status.NVAPI_PROFILE_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_SETTING_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_EXECUTABLE_NOT_FOUND: 404,
    NvAPI_Status.NVAPI_SETTING_NOT_FOUND_NO_DEFAULT: 404,
    NvAPI_Status.NVAPI_INVALID_ARGUMENT: 400,
    NvAPI_Status.NVAPI_PROFILE_NAME_IN_USE: 409,
    NvAPI_Status.NVAPI_EXECUTABLE_ALREADY_IN_USE: 409,
}


# ---- Route table --------------------------------------------------------

def _match(template: str, path: str) -> dict | None:
    """Match a path against a template, returning extracted params or None."""
    t_parts = template.strip("/").split("/")
    p_parts = path.strip("/").split("/")
    if len(t_parts) != len(p_parts):
        return None
    params: dict = {}
    for t, p in zip(t_parts, p_parts):
        if t.startswith("{") and t.endswith("}"):
            spec = t[1:-1]
            if ":" in spec:
                name, typ = spec.split(":", 1)
                if typ == "int":
                    try:
                        params[name] = int(p)
                    except ValueError:
                        return None
                else:
                    params[name] = unquote(p)
            else:
                params[spec] = unquote(p)
        elif t != unquote(p):
            return None
    return params


# (method, template, handler, needs_auth)
# More-specific routes must come before less-specific ones.
ROUTES: list[tuple[str, str, str, bool]] = [
    # GPU
    ("GET",    "/gpu",                                          "_h_get_gpus",            False),
    # Base profile
    ("GET",    "/base/settings/{setting_id:int}",               "_h_get_base_setting",    False),
    ("PUT",    "/base/settings/{setting_id:int}",               "_h_set_base_setting",    True),
    ("DELETE", "/base/settings/{setting_id:int}",               "_h_del_base_setting",    True),
    ("GET",    "/base",                                         "_h_get_base",            False),
    # Profiles
    ("GET",    "/profiles/{name}/settings/{setting_id:int}",    "_h_get_profile_setting", False),
    ("PUT",    "/profiles/{name}/settings/{setting_id:int}",    "_h_set_profile_setting", True),
    ("DELETE", "/profiles/{name}/settings/{setting_id:int}",    "_h_del_profile_setting", True),
    ("GET",    "/profiles/{name}/apps",                         "_h_list_apps",           False),
    ("POST",  "/profiles/{name}/apps",                          "_h_add_app",             True),
    ("DELETE", "/profiles/{name}/apps",                         "_h_remove_app",          True),
    ("GET",    "/profiles/{name}",                              "_h_get_profile",         False),
    ("POST",  "/profiles",                                      "_h_create_profile",      True),
    ("DELETE", "/profiles/{name}",                              "_h_delete_profile",      True),
    ("GET",    "/profiles",                                     "_h_list_profiles",       False),
    # Display
    ("PUT",    "/display/saturation",                           "_h_set_saturation",      True),
    ("PUT",    "/display/resolution",                           "_h_set_resolution",      True),
    ("POST",  "/display/preset/gaming",                         "_h_gaming_preset",       True),
    ("POST",  "/display/preset/desktop",                        "_h_desktop_preset",      True),
    ("POST",  "/display/fix-refresh",                           "_h_fix_refresh",         True),
    ("GET",    "/display",                                      "_h_get_display",         False),
    # Settings IDs
    ("GET",    "/settings/ids",                                 "_h_setting_ids",         False),
    # Shutdown
    ("POST",  "/shutdown",                                      "_h_shutdown",            True),
]


# ---- Handler -------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    """Single-threaded JSON request handler."""

    # Suppress default stderr logging
    def log_message(self, format, *args):
        pass

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def send_error(self, code, message=None, explain=None):
        self._send_error_response(code, message or "bad request")

    # --- Helpers ---

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self._add_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_no_content(self) -> None:
        self.send_response(204)
        self.send_header("Connection", "close")
        self._add_cors_headers()
        self.end_headers()

    def _send_error_response(self, status: int, detail: str) -> None:
        self._send_json({"detail": detail}, status)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY:
            raise ValidationError("request body too large")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValidationError("invalid JSON body")
        if not isinstance(data, dict):
            raise ValidationError("request body must be a JSON object")
        return data

    def _add_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin == _ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Credentials", "true")

    def _check_auth(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not secrets.compare_digest(
            auth[7:], _TOKEN
        ):
            self._send_error_response(401, "unauthorized")
            return False
        return True

    def _check_throttle(self) -> bool:
        global _last_write
        now = time.monotonic()
        if now - _last_write < _MIN_INTERVAL:
            self._send_error_response(429, "too many requests")
            return False
        _last_write = now
        return True

    def _nvapi(self, func, *args, **kwargs):
        """Call a service function, mapping NvAPIError to HTTP status."""
        try:
            result = func(*args, **kwargs)
            return result if result is not None else True
        except NvAPIError as e:
            logger.warning("NvAPIError in %s: %s", func.__name__, e)
            code = _STATUS_TO_HTTP.get(e.status, 500)
            self._send_error_response(code, "operation failed")
            return None
        except SetupAPIError as e:
            logger.warning("SetupAPIError in %s: %s", func.__name__, e)
            self._send_error_response(500, str(e))
            return None

    # --- Dispatch ---

    def _dispatch(self, method: str) -> None:
        path = self.path.split("?", 1)[0]  # strip query string
        allowed_methods = []
        for route_method, template, handler_name, needs_auth in ROUTES:
            params = _match(template, path)
            if params is None:
                continue
            if route_method != method:
                allowed_methods.append(route_method)
                continue
            if needs_auth:
                if not self._check_auth():
                    return
                if not self._check_throttle():
                    return
            try:
                getattr(self, handler_name)(**params)
            except ValidationError as e:
                self._send_error_response(422, e.detail)
            return
        if allowed_methods:
            self.send_response(405)
            self.send_header("Allow", ", ".join(sorted(set(allowed_methods))))
            self.send_header("Content-Type", "application/json")
            body = json.dumps({"detail": "method not allowed"}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self._add_cors_headers()
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_error_response(404, "not found")

    def do_GET(self):
        self._dispatch("GET")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin == _ALLOWED_ORIGIN:
            self.send_header("Access-Control-Allow-Origin", _ALLOWED_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    # --- Route handlers ---

    # GPU
    def _h_get_gpus(self):
        result = self._nvapi(service.list_gpus)
        if result is not None:
            self._send_json(result)

    # Base profile
    def _h_get_base(self):
        result = self._nvapi(service.get_base_profile)
        if result is not None:
            self._send_json(result)

    def _h_get_base_setting(self, setting_id: int):
        result = self._nvapi(service.get_base_setting, setting_id)
        if result is not None:
            self._send_json(result)

    def _h_set_base_setting(self, setting_id: int):
        body = validate_set_setting(self._read_body())
        result = self._nvapi(service.set_base_setting, setting_id, body["value"])
        if result is not None:
            self._send_json(result)

    def _h_del_base_setting(self, setting_id: int):
        result = self._nvapi(service.delete_base_setting, setting_id)
        if result is not None:
            self._send_no_content()

    # Profiles
    def _h_list_profiles(self):
        result = self._nvapi(service.list_profiles)
        if result is not None:
            self._send_json(result)

    def _h_get_profile(self, name: str):
        result = self._nvapi(service.get_profile, name)
        if result is not None:
            self._send_json(result)

    def _h_create_profile(self):
        body = validate_create_profile(self._read_body())
        result = self._nvapi(service.create_profile, body["name"])
        if result is not None:
            self._send_json(result, 201)

    def _h_delete_profile(self, name: str):
        result = self._nvapi(service.delete_profile, name)
        if result is not None:
            self._send_no_content()

    # Profile settings
    def _h_get_profile_setting(self, name: str, setting_id: int):
        result = self._nvapi(service.get_setting, name, setting_id)
        if result is not None:
            self._send_json(result)

    def _h_set_profile_setting(self, name: str, setting_id: int):
        body = validate_set_setting(self._read_body())
        result = self._nvapi(service.set_setting, name, setting_id, body["value"])
        if result is not None:
            self._send_json(result)

    def _h_del_profile_setting(self, name: str, setting_id: int):
        result = self._nvapi(service.delete_setting, name, setting_id)
        if result is not None:
            self._send_no_content()

    # Profile apps
    def _h_list_apps(self, name: str):
        result = self._nvapi(service.list_apps, name)
        if result is not None:
            self._send_json(result)

    def _h_add_app(self, name: str):
        body = validate_app_request(self._read_body())
        result = self._nvapi(service.add_app, name, body["exe"])
        if result is not None:
            self._send_json({"detail": "created"}, 201)

    def _h_remove_app(self, name: str):
        body = validate_app_request(self._read_body())
        result = self._nvapi(service.remove_app, name, body["exe"])
        if result is not None:
            self._send_no_content()

    # Display
    def _h_get_display(self):
        result = self._nvapi(service.get_display_info)
        if result is not None:
            self._send_json(result)

    def _h_set_saturation(self):
        body = validate_set_saturation(self._read_body())
        result = self._nvapi(service.set_saturation, body["level"])
        if result is not None:
            self._send_json(result)

    def _h_set_resolution(self):
        body = validate_set_resolution(self._read_body())
        result = self._nvapi(service.set_resolution, body["width"], body["height"], body["refresh"], body["stretch"])
        if result is not None:
            self._send_json(result)

    def _h_gaming_preset(self):
        body = validate_gaming_preset(self._read_body())
        result = self._nvapi(
            service.apply_gaming_preset,
            width=body["width"],
            height=body["height"],
            saturation=body["saturation"],
            refresh=body["refresh"],
            stretch=body["stretch"],
            disable_monitor=body["disable_monitor"],
            stop_glazewm=body["stop_glazewm"],
            disable_borders=body["disable_borders"],
            fix_refresh=body["fix_refresh"],
            skip_devices=body["skip_devices"],
        )
        if result is not None:
            self._send_json(result)

    def _h_desktop_preset(self):
        body = validate_desktop_preset(self._read_body())
        result = self._nvapi(
            service.apply_desktop_preset,
            saturation=body["saturation"],
            enable_monitor=body["enable_monitor"],
            start_glazewm=body["start_glazewm"],
            enable_borders=body["enable_borders"],
            fix_refresh=body["fix_refresh"],
            skip_devices=body["skip_devices"],
        )
        if result is not None:
            self._send_json(result)

    def _h_fix_refresh(self):
        body = self._read_body()
        skip = body.get("skip_devices", [])
        if not isinstance(skip, list) or not all(isinstance(s, str) for s in skip):
            self._send_error_response(422, "skip_devices must be an array of strings")
            return
        result = self._nvapi(service.fix_refresh_rates, skip or None)
        if result is not None:
            self._send_json(result)

    # Settings IDs
    def _h_setting_ids(self):
        result = [
            {"id": sid, "idHex": f"0x{sid:08X}", "name": name}
            for sid, name in sorted(SETTING_IDS.items())
        ]
        self._send_json(result)

    # Shutdown
    def _h_shutdown(self):
        self._send_json({"detail": "shutting down"}, 202)
        self.server._stop = True


# ---- Server ---------------------------------------------------------------

class NvidiotServer(HTTPServer):
    allow_reuse_address = True
    _stop = False

    def serve_until_stopped(self) -> None:
        self.timeout = 0.5
        while not self._stop:
            self.handle_request()
        self.server_close()
