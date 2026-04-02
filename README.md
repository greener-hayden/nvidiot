# nvidiot

**Zero-dependency REST API for NVIDIA GPU and driver settings.**

![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen)
![Windows](https://img.shields.io/badge/platform-Windows-0078d4?logo=windows&logoColor=white)

---

nvidiot wraps the NVIDIA Control Panel driver settings through [NVAPI](https://developer.nvidia.com/nvapi) (`nvapi64.dll`) using ctypes FFI.
It exposes GPU info, driver profiles, DRS settings, and display configuration as a local REST API — useful for automation scripts, status bar widgets, and gaming presets.

Runs on `127.0.0.1:8000` only. Not reachable from the network.

## Features

- **Full DRS access** — read, write, and delete settings in the global profile or any application profile
- **Display control** — resolution, refresh rate, and digital vibrance
- **Gaming presets** — one-call endpoints to swap between gaming and desktop display configs
- **Self-installing** — `nvidiot install` registers as a logon scheduled task, `nvidiot uninstall` removes it
- **Opt-in auth** — off by default; enable with `--secure` to require a bearer token for write endpoints
- **Single binary** — builds to a standalone `.exe` via PyInstaller, no runtime dependencies

## Quick Start

### Download

Grab the latest `.exe` from [Releases](../../releases). Run it:

```
nvidiot.exe
```

The server starts on `http://127.0.0.1:8000`. No auth required by default — all endpoints are open.

> **Note:** The binary is not code-signed. Windows SmartScreen may warn on first run. Each release includes a `.sha256` checksum file to verify the download.

### Install as a scheduled task

To run nvidiot automatically at logon:

```
nvidiot.exe install
```

This requests admin via UAC, then:
- Copies the `.exe` to `%LOCALAPPDATA%\nvidiot\`
- Registers a Windows scheduled task that starts at logon with admin privileges
- Drops a `nvidiot.cmd` wrapper in `~/.local/bin/` so you can run `nvidiot` from anywhere

Admin is needed because writing global NVIDIA driver profiles and toggling monitors requires elevation.

To remove:

```
nvidiot.exe uninstall
```

### From source

```bash
pip install -e ".[dev]"
python main.py
```

## Authentication

Auth is **off by default**. Since the server only listens on localhost, this is low-risk and keeps the setup frictionless.

To enable auth, use any of these:

| Method | What happens |
|--------|-------------|
| `nvidiot --secure` | Generates a new token and writes it to `~/.nvidiot-token` |
| `NVIDIOT_TOKEN=<value>` env var | Uses that token, writes it to `~/.nvidiot-token` |
| `~/.nvidiot-token` exists | Reads the token from the file |

When auth is enabled:

| Scope | Auth |
|-------|------|
| `GET` endpoints | **None** — safe for status bar widgets |
| `PUT` / `POST` / `DELETE` | `Authorization: Bearer <token>` |

The token file is ACL-restricted to the current user (`icacls /inheritance:r /grant:r <user>:(F)`).

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
| `PUT` | `/display/saturation` | Set digital vibrance (0-100) |
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
      |
nvapi/service.py    Business logic, DRS session lifecycle, plain dicts
      |
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
- Python 3.11+ (for running from source)

## License

[MIT](LICENSE)
