# Auth token is written to ~/.nvidiot-token on startup.
# GET endpoints (metrics, display info) require no auth.
# PUT/POST/DELETE endpoints require: Authorization: Bearer <token>
# Zebar widgets only need GET — no token needed for status bar display.
# To call write endpoints from scripts:
#   $token = Get-Content "$env:USERPROFILE\.nvidiot-token"
#   curl -H "Authorization: Bearer $token" -X POST http://127.0.0.1:8000/shutdown

"""Uvicorn entrypoint for the nvidiot API."""

import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import init_token
from api.routes import read_router, write_router

# --- Token setup ---
TOKEN = os.environ.get("NVIDIOT_TOKEN") or secrets.token_urlsafe(32)
TOKEN_PATH = Path.home() / ".nvidiot-token"

init_token(TOKEN)

app = FastAPI(
    title="nvidiot",
    description="REST API wrapping NVIDIA Control Panel settings via NVAPI",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:6124"],
    allow_methods=["GET", "PUT", "POST", "DELETE"],
    allow_headers=["Authorization"],
)

app.include_router(read_router)
app.include_router(write_router)

HOST = "127.0.0.1"
PORT = 8000


def _write_token_file() -> None:
    """Write the auth token to ~/.nvidiot-token with restrictive permissions."""
    fd = os.open(str(TOKEN_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, TOKEN.encode())
    finally:
        os.close(fd)
    print(f"Auth token written to {TOKEN_PATH}")


def _replace_existing_instance() -> None:
    """If another nvidiot is running on our port, ask it to shut down."""
    import json
    import socket
    import sys
    import time
    import urllib.request
    import urllib.error

    base = f"http://{HOST}:{PORT}"

    # Quick check: is anything listening on the port?
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((HOST, PORT))
    finally:
        sock.close()
    if result != 0:
        return  # port free, nothing to do

    # Port is bound — try health probe to confirm it's nvidiot
    is_nvidiot = False
    try:
        req = urllib.request.Request(f"{base}/gpu", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            body = json.loads(resp.read())
            if isinstance(body, list) and body and "name" in body[0]:
                is_nvidiot = True
    except Exception:
        pass

    if is_nvidiot:
        # Healthy instance — ask it to shut down gracefully
        old_token = None
        try:
            old_token = TOKEN_PATH.read_text().strip()
        except Exception:
            pass

        print(f"Existing nvidiot instance on :{PORT}, requesting shutdown...")
        try:
            req = urllib.request.Request(f"{base}/shutdown", method="POST")
            if old_token:
                req.add_header("Authorization", f"Bearer {old_token}")
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception:
            pass  # may close connection before responding
    else:
        # Port held by a broken/stale nvidiot or unknown process — try
        # killing nvidiot by name as a fallback before giving up.
        import subprocess
        print(f"Port {PORT} in use by unresponsive process, attempting cleanup...")
        subprocess.run(
            ["taskkill", "/F", "/IM", "nvidiot.exe"],
            capture_output=True,
        )

    # Wait for port to free
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        time.sleep(0.25)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            if sock.connect_ex((HOST, PORT)) != 0:
                print("Previous instance stopped.")
                return
        finally:
            sock.close()

    print(
        f"WARNING: port {PORT} still in use after 5s. Exiting.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    import uvicorn

    _replace_existing_instance()
    _write_token_file()
    uvicorn.run(app, host=HOST, port=PORT)
