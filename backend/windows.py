"""Which Memory pop-up/app windows (opened from the desktop wallpaper) are currently open.

The wallpaper locks its brain controls while any are open: Lively keeps forwarding mouse movement to the wallpaper
even when another window has focus, so dragging a pop-up around would otherwise spin the brain.
Windows heartbeat every ~10 s and send a beacon when they close; silent ones expire after TIMEOUT seconds.
"""
from __future__ import annotations

import threading
import time

from .reminders import bus

TIMEOUT = 25.0
_open: dict[str, float] = {}
_lock = threading.Lock()


def _publish(n: int) -> None:
    bus.publish("windows", {"open": n})


def count() -> int:
    prune()
    with _lock:
        return len(_open)


def alive(pid: str) -> None:
    with _lock:
        new = pid not in _open
        _open[pid] = time.monotonic()
        n = len(_open)
    if new:
        _publish(n)


def closed(pid: str) -> None:
    with _lock:
        gone = _open.pop(pid, None) is not None
        n = len(_open)
    if gone:
        _publish(n)


def prune() -> None:
    now = time.monotonic()
    with _lock:
        stale = [p for p, seen in _open.items() if now - seen > TIMEOUT]
        for p in stale:
            del _open[p]
        n = len(_open)
    if stale:
        _publish(n)
