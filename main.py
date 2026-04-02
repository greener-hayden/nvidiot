# nvidiot — local REST API for NVIDIA GPU settings.
#
# Usage:
#   nvidiot                Start the server on 127.0.0.1:8000
#   nvidiot --secure       Start with bearer-token auth enabled
#   nvidiot install         Install to %LOCALAPPDATA%\nvidiot and register as a logon task
#   nvidiot install --secure  Install with auth enabled
#   nvidiot uninstall       Stop and remove the scheduled task
#
# Auth is off by default (localhost-only, low risk). It activates when:
#   - ~/.nvidiot-token exists at startup (token read from file)
#   - NVIDIOT_TOKEN env var is set (token written to file)
#   - --secure flag is passed (new token generated and written to file)

"""Stdlib HTTP server entrypoint for the nvidiot API."""

import ctypes
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from api.server import NvidiotServer, Handler, init_token

HOST = "127.0.0.1"
PORT = 8000
TOKEN_PATH = Path.home() / ".nvidiot-token"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "nvidiot"
BIN_DIR = Path.home() / ".local" / "bin"
TASK_NAME = "nvidiot"


# --- Auth setup ---

def _write_token_file(token: str) -> None:
    """Write the auth token to ~/.nvidiot-token with restrictive permissions."""
    TOKEN_PATH.write_text(token)
    subprocess.run(
        ["icacls", str(TOKEN_PATH), "/inheritance:r",
         "/grant:r", f"{os.getlogin()}:(F)"],
        capture_output=True,
    )
    print(f"Auth token written to {TOKEN_PATH}")


def _setup_auth(secure: bool) -> None:
    """Configure auth based on env var, token file, or --secure flag."""
    token = os.environ.get("NVIDIOT_TOKEN")

    if token:
        _write_token_file(token)
        init_token(token)
    elif TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text().strip()
        init_token(token)
        print(f"Auth enabled (token from {TOKEN_PATH})")
    elif secure:
        token = secrets.token_urlsafe(32)
        _write_token_file(token)
        init_token(token)


# --- Instance replacement ---

def _replace_existing_instance(exit_on_failure: bool = True) -> None:
    """If another nvidiot is running on our port, ask it to shut down."""
    base = f"http://{HOST}:{PORT}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((HOST, PORT))
    finally:
        sock.close()
    if result != 0:
        return

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
            pass
    else:
        # Port held by unknown process — kill by PID, not image name
        print(f"Port {PORT} in use by unresponsive process, attempting cleanup...")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$p = (Get-NetTCPConnection -LocalPort {PORT} "
             f"-ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess; "
             f"if ($p) {{ Stop-Process -Id $p -Force }}"],
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

    if exit_on_failure:
        print(f"WARNING: port {PORT} still in use after 5s. Exiting.", file=sys.stderr)
        sys.exit(1)


# --- Install / uninstall ---

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate_and_rerun() -> None:
    """Re-launch the current command with admin privileges via UAC."""
    exe = sys.executable
    args = subprocess.list2cmdline(sys.argv[1:])
    # ShellExecuteW returns >32 on success
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
    sys.exit(0 if ret > 32 else 1)


def _cmd_install(secure: bool) -> None:
    """Install nvidiot to LOCALAPPDATA and register as a logon scheduled task."""
    if not _is_admin():
        _elevate_and_rerun()

    # Copy exe
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    dest = INSTALL_DIR / "nvidiot.exe"
    src = Path(sys.executable)
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
        print(f"Copied to {dest}")
    else:
        print(f"Already installed at {dest}")

    # Drop wrapper script in ~/.local/bin
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    cmd_path = BIN_DIR / "nvidiot.cmd"
    cmd_path.write_text(
        '@echo off\n'
        f'"%LOCALAPPDATA%\\nvidiot\\nvidiot.exe" %*\n'
        'exit /b %ERRORLEVEL%\n'
    )
    print(f"Wrapper written to {cmd_path}")

    # Set up auth if requested
    if secure:
        token = secrets.token_urlsafe(32)
        _write_token_file(token)

    # Register scheduled task
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
    )
    subprocess.run(
        ["schtasks", "/Create",
         "/TN", TASK_NAME,
         "/TR", f'"{dest}"',
         "/SC", "ONLOGON",
         "/RL", "HIGHEST",
         "/F"],
        capture_output=True,
    )
    print(f"Scheduled task '{TASK_NAME}' registered (runs at logon with admin)")

    # Start it now
    subprocess.run(
        ["schtasks", "/Run", "/TN", TASK_NAME],
        capture_output=True,
    )
    print("nvidiot is running.")


def _cmd_uninstall() -> None:
    """Stop nvidiot and remove the scheduled task."""
    if not _is_admin():
        _elevate_and_rerun()

    _replace_existing_instance(exit_on_failure=False)

    # Remove scheduled task
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
    )
    print(f"Scheduled task '{TASK_NAME}' removed.")
    print("To fully remove, delete the folder: " + str(INSTALL_DIR))


# --- Entry point ---

if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a.lower() for a in sys.argv[1:] if a.startswith("-")]
    secure = "--secure" in flags
    command = args[0] if args else "serve"

    if command == "install":
        _cmd_install(secure)
    elif command == "uninstall":
        _cmd_uninstall()
    elif command == "serve":
        _replace_existing_instance()
        _setup_auth(secure)
        print(f"Listening on http://{HOST}:{PORT}")
        server = NvidiotServer((HOST, PORT), Handler)
        try:
            server.serve_until_stopped()
        except KeyboardInterrupt:
            server.server_close()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nvidiot [install|uninstall] [--secure]")
        sys.exit(1)
