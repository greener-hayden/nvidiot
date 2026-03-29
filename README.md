# nvidiot

## Quick Start

```bash
pip install -e ".[dev]"
python main.py
```

Starts on `http://127.0.0.1:8000`. Writes a bearer token to `~/.nvidiot-token` on startup and gracefully replaces any existing instance.

## Auth

- **GET** endpoints require **no auth** — safe for status bar widgets.
- **PUT/POST/DELETE** require `Authorization: Bearer <token>`.

```powershell
$token = Get-Content "$env:USERPROFILE\.nvidiot-token"
curl -H "Authorization: Bearer $token" -X POST http://127.0.0.1:8000/shutdown
```

## Endpoints

| Method | Path | |
|--------|------|-|
| GET | `/gpu` | GPUs with temperatures |
| GET | `/base` | Global profile settings |
| GET | `/base/settings/{id}` | Read a global setting |
| PUT | `/base/settings/{id}` | Write a global setting |
| DELETE | `/base/settings/{id}` | Delete a global setting override |
| GET | `/profiles` | List profiles |
| GET | `/profiles/{name}` | Profile detail with settings and apps |
| POST | `/profiles` | Create profile |
| DELETE | `/profiles/{name}` | Delete profile |
| GET | `/profiles/{name}/settings/{id}` | Read profile setting |
| PUT | `/profiles/{name}/settings/{id}` | Write profile setting |
| DELETE | `/profiles/{name}/settings/{id}` | Delete profile setting |
| GET | `/profiles/{name}/apps` | List apps |
| POST | `/profiles/{name}/apps` | Add app |
| DELETE | `/profiles/{name}/apps` | Remove app |
| GET | `/display` | Resolution, refresh, saturation |
| PUT | `/display/saturation` | Set digital vibrance (0-100) |
| PUT | `/display/resolution` | Set resolution and refresh rate |
| POST | `/display/preset/gaming` | Gaming preset (res + saturation) |
| POST | `/display/preset/desktop` | Restore native res and default saturation |
| GET | `/settings/ids` | Known DRS setting IDs |
| POST | `/shutdown` | Shut down server |

## Architecture

1. **`nvapi/ffi.py`** — ctypes bindings to `nvapi64.dll` via `nvapi_QueryInterface`
2. **`nvapi/service.py`** — business logic returning plain dicts
3. **`api/server.py`** — stdlib HTTP server and JSON route handlers

## Testing

- **`tests/test_unit.py`** — validation and helpers with mocked DLL (no GPU)
- **`tests/test_api.py`** and other integration tests — real NVIDIA hardware

```bash
pytest
```
