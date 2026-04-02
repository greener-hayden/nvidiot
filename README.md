# nvidiot

**Zero-dependency REST API for NVIDIA GPU and driver settings.**
No SDK install, no C compilation — just an NVIDIA GPU with drivers and `python main.py`.

![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen)
![Windows](https://img.shields.io/badge/platform-Windows-0078d4?logo=windows&logoColor=white)

---

nvidiot wraps the NVIDIA Control Panel driver settings through [NVAPI](https://developer.nvidia.com/rtx/nvapi) (`nvapi64.dll`) using ctypes FFI.
It exposes GPU info, driver profiles, DRS settings, and display configuration as a local REST API — useful for automation scripts, status bar widgets, and gaming presets.

## Features

- **Full DRS access** — read, write, and delete settings in the global profile or any application profile
- **Display control** — resolution, refresh rate, and digital vibrance
- **Gaming presets** — one-call endpoints to swap between gaming and desktop display configs
- **Auto-auth** — generates a bearer token on startup; GET endpoints stay open for widget polling
- **Graceful takeover** — detects and replaces any existing instance on the same port
- **Single binary** — builds to a standalone `.exe` via PyInstaller, with optional scheduled task registration

## Quick Start

```bash
pip install -e ".[dev]"
python main.py
```

Starts on `http://127.0.0.1:8000`. A bearer token is written to `~/.nvidiot-token` on startup.

### Standalone Build

```bash
# Requires Task (https://taskfile.dev)
task build        # Build dist/nvidiot.exe
task install      # Build, install, and register as a logon scheduled task
task uninstall    # Stop and remove the scheduled task
```

## Authentication

| Scope | Auth |
|-------|------|
| `GET` endpoints | **None** — safe for status bar widgets |
| `PUT` / `POST` / `DELETE` | `Authorization: Bearer <token>` |

```powershell
$token = Get-Content "$env:USERPROFILE\.nvidiot-token"
curl -H "Authorization: Bearer $token" -X POST http://127.0.0.1:8000/shutdown
```

## API Reference

### GPU

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/gpu` | List GPUs with temperatures |

### Global Profile

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/base` | Global profile settings |
| `GET` | `/base/settings/{id}` | Read a global setting |
| `PUT` | `/base/settings/{id}` | Write a global setting |
| `DELETE` | `/base/settings/{id}` | Delete a global setting override |

### Application Profiles

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/profiles` | List all profiles |
| `GET` | `/profiles/{name}` | Profile detail with settings and apps |
| `POST` | `/profiles` | Create a profile |
| `DELETE` | `/profiles/{name}` | Delete a profile |
| `GET` | `/profiles/{name}/settings/{id}` | Read a profile setting |
| `PUT` | `/profiles/{name}/settings/{id}` | Write a profile setting |
| `DELETE` | `/profiles/{name}/settings/{id}` | Delete a profile setting |
| `GET` | `/profiles/{name}/apps` | List apps in a profile |
| `POST` | `/profiles/{name}/apps` | Add an app to a profile |
| `DELETE` | `/profiles/{name}/apps` | Remove an app from a profile |

### Display

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/display` | Resolution, refresh rate, and saturation |
| `PUT` | `/display/saturation` | Set digital vibrance (0–100) |
| `PUT` | `/display/resolution` | Set resolution and refresh rate |
| `POST` | `/display/preset/gaming` | Apply gaming preset (res + saturation) |
| `POST` | `/display/preset/desktop` | Restore native res and default saturation |
| `POST` | `/display/fix-refresh` | Set all monitors to max refresh for current res |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/settings/ids` | Known DRS setting IDs |
| `POST` | `/shutdown` | Shut down the server |

## Architecture

Three layers, each calling only the one below:

```
api/server.py       Stdlib HTTP server, routing, auth, JSON responses
      │
nvapi/service.py    Business logic, DRS session lifecycle, plain dicts
      │
nvapi/ffi.py        ctypes bindings to nvapi64.dll via QueryInterface
```

Supporting modules:

- `nvapi/constants.py` — status codes, function IDs, DRS setting IDs and value enums
- `nvapi/setupapi.py` — monitor detection via Windows SetupAPI
- `api/validate.py` — request body validation

## Testing

```bash
pytest                          # All tests (needs NVIDIA GPU for integration)
pytest tests/test_unit.py       # Unit tests only (mocked DLL, no GPU needed)
pytest tests/test_api.py        # Integration tests (real hardware)
```

## Requirements

- Windows with an NVIDIA GPU and drivers installed
- Python 3.11+

## License

[MIT](LICENSE)
