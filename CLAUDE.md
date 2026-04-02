# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

nvidiot is a REST API that wraps NVIDIA Control Panel driver settings via the NVAPI library (`nvapi64.dll`). It uses ctypes FFI and Python's stdlib `http.server` — zero third-party runtime dependencies, no C compilation or NVIDIA SDK installation required, just an NVIDIA GPU with drivers installed.

## Commands

```bash
# Run the API server (port 8000)
task dev            # or: python main.py

# Run all tests (requires NVIDIA GPU — tests hit real hardware)
pytest

# Run a single test
pytest tests/test_api.py::test_get_gpus

# Build standalone .exe
task build

# Install .exe + register as scheduled task (requires admin)
task install

# Bump version and push (workflow auto-creates tag + release)
task release -- 0.2.0

# Install dev dependencies (without Taskfile)
pip install -e ".[dev]"
```

## Architecture

Three-layer design, each layer only calls the one below it:

1. **`nvapi/ffi.py`** — Raw ctypes bindings. All NVAPI functions are resolved at runtime via `nvapi_QueryInterface`, the single export from `nvapi64.dll`. Function pointers are cached in `_cache` by ID. Every function calls `_check()` which raises `NvAPIError` on non-OK status.

2. **`nvapi/service.py`** — Pythonic business logic. The `drs_session()` context manager handles the DRS lifecycle (create → load → yield → save if needed → destroy). All public functions call `_ensure_initialized()` first. Returns plain dicts.

3. **`api/server.py`** — Stdlib HTTP server and route handlers. Uses `http.server.BaseHTTPRequestHandler` with a route table for dispatch. Auth (Bearer token) and write throttle are inlined. All route handlers delegate to `service.*` through `_nvapi()`, which catches `NvAPIError` and maps to HTTP status codes.

Supporting files:
- **`nvapi/constants.py`** — `NvAPI_Status` enum, `NVAPI_FUNC_IDS` (QueryInterface lookup table), `SETTING_IDS` (well-known DRS setting IDs), setting value enums
- **`nvapi/setupapi.py`** — SetupAPI ctypes bindings for monitor enable/disable via Windows device manager
- **`api/validate.py`** — Plain validation functions for request bodies (replaces Pydantic models)
- **`main.py`** — Entrypoint. Generates auth token (written to `~/.nvidiot-token` with restricted ACLs), detects port conflicts, and gracefully replaces any running instance before starting

## Key Patterns

- **Adding a new NVAPI function**: Add its ID to `NVAPI_FUNC_IDS` in `constants.py`, then create a wrapper in `ffi.py` using `_query(_id("FuncName"), return_type, [arg_types])`.
- **Struct versioning**: NVDRS struct versions are computed as `sizeof(struct) | (ver_num << 16)`. Always set `.version` before passing to NVAPI.
- **Settings use DWORD type by default** for set operations (see `set_setting` / `set_base_setting` in service.py).
- **Tests**: `test_api.py` requires a real NVIDIA GPU (starts a server on port 18000). `test_unit.py` mocks the DLL and runs a test server on port 18001. Tests that modify settings save and restore original values. Additional test files: `test_ffi_init.py` (DLL load), `test_ffi_session.py` (session ops), `test_service.py` (setting round-trips) — all require a GPU.
- **Zero runtime dependencies** — only stdlib. Dev deps are `pytest` and `pyinstaller`.
- **Write throttle**: All mutating endpoints enforce a 500ms minimum interval (`_MIN_INTERVAL` in server.py). Returns 429 if violated.
- **CORS**: Hardcoded allowed origin `http://127.0.0.1:6124` (Zebar status bar widget). Preflight handled via `do_OPTIONS`.
- **Error mapping**: `_STATUS_TO_HTTP` in server.py maps `NvAPIError` status codes to HTTP (404 for not-found variants, 400 for invalid args, 409 for name/exe conflicts, 500 for everything else).
- **Presets**: `apply_gaming_preset()` and `apply_desktop_preset()` in service.py have side effects beyond DRS settings — they can toggle monitors via SetupAPI and start/stop glazewm.
- **Release workflow**: `.github/workflows/release.yml` triggers when `pyproject.toml` is pushed to `main`. It reads the version, creates a `v*` tag if new, builds the `.exe` on `windows-latest`, and creates a GitHub release with the artifact and checksum.
