"""Plain validation functions — replaces Pydantic models."""


class ValidationError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _require_int(data: dict, key: str, label: str | None = None) -> int:
    label = label or key
    v = data.get(key)
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValidationError(f"{label} must be an integer")
    return v


def _require_str(data: dict, key: str, min_len: int, max_len: int) -> str:
    v = data.get(key)
    if not isinstance(v, str):
        raise ValidationError(f"{key} must be a string")
    if len(v) < min_len or len(v) > max_len:
        raise ValidationError(f"{key} must be {min_len}-{max_len} characters")
    return v


def _int_range(data: dict, key: str, lo: int, hi: int, default=...) -> int | None:
    v = data.get(key, default)
    if v is ... :
        raise ValidationError(f"{key} is required")
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool):
        raise ValidationError(f"{key} must be an integer")
    if v < lo or v > hi:
        raise ValidationError(f"{key} must be between {lo} and {hi}")
    return v


def validate_set_setting(data: dict) -> dict:
    return {"value": _require_int(data, "value")}


def validate_create_profile(data: dict) -> dict:
    return {"name": _require_str(data, "name", 1, 2000)}


def validate_app_request(data: dict) -> dict:
    return {"exe": _require_str(data, "exe", 1, 260)}


def validate_set_saturation(data: dict) -> dict:
    return {"level": _int_range(data, "level", 0, 100)}


def validate_set_resolution(data: dict) -> dict:
    return {
        "width": _int_range(data, "width", 640, 15360),
        "height": _int_range(data, "height", 480, 8640),
        "refresh": _int_range(data, "refresh", 24, 600, default=None),
        "stretch": _opt_bool(data, "stretch", default=True),
    }


def _opt_bool(data: dict, key: str, default: bool = False) -> bool:
    v = data.get(key, default)
    if not isinstance(v, bool):
        raise ValidationError(f"{key} must be a boolean")
    return v


def _opt_str_list(data: dict, key: str) -> list[str]:
    v = data.get(key, [])
    if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
        raise ValidationError(f"{key} must be an array of strings")
    return v


def validate_gaming_preset(data: dict) -> dict:
    return {
        "width": _int_range(data, "width", 640, 15360),
        "height": _int_range(data, "height", 480, 8640),
        "saturation": _int_range(data, "saturation", 0, 100, default=90),
        "refresh": _int_range(data, "refresh", 24, 600, default=None),
        "stretch": _opt_bool(data, "stretch", default=True),
        "disable_monitor": _opt_bool(data, "disable_monitor"),
        "stop_glazewm": _opt_bool(data, "stop_glazewm"),
        "disable_borders": _opt_bool(data, "disable_borders"),
        "fix_refresh": _opt_bool(data, "fix_refresh"),
        "skip_devices": _opt_str_list(data, "skip_devices"),
    }


def validate_desktop_preset(data: dict) -> dict:
    return {
        "saturation": _int_range(data, "saturation", 0, 100, default=50),
        "enable_monitor": _opt_bool(data, "enable_monitor"),
        "start_glazewm": _opt_bool(data, "start_glazewm"),
        "enable_borders": _opt_bool(data, "enable_borders"),
        "fix_refresh": _opt_bool(data, "fix_refresh"),
        "skip_devices": _opt_str_list(data, "skip_devices"),
    }


def validate_fix_refresh(data: dict) -> dict:
    return {"skip_devices": _opt_str_list(data, "skip_devices")}
