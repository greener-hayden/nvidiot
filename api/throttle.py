"""Simple time-based write cooldown."""

import time
from fastapi import HTTPException

_last_write = 0.0
MIN_INTERVAL = 0.5


def throttle_writes() -> None:
    global _last_write
    now = time.monotonic()
    if now - _last_write < MIN_INTERVAL:
        raise HTTPException(status_code=429, detail="too many requests")
    _last_write = now
