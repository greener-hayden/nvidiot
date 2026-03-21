"""Bearer token authentication for write endpoints."""

import secrets
from fastapi import HTTPException, Request

TOKEN: str = ""


def init_token(token: str) -> None:
    global TOKEN
    TOKEN = token


def require_token(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or not secrets.compare_digest(
        auth[7:], TOKEN
    ):
        raise HTTPException(status_code=401, detail="unauthorized")
