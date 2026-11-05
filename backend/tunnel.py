"""Keep a Microsoft Dev Tunnel open to Memory, so a Power Automate cloud flow can reach POST /api/planner/sync.

When Settings has a tunnel ID (e.g. "memory-sync"), Memory runs `devtunnel host <id>` in the background with no
window, reads the public URL from its output, and restarts it (with a growing delay) if it stops. The tunnel itself
is created once with the devtunnel CLI (see README). Through the tunnel, Memory's access guard only lets the sync
endpoint through, and that needs the sync token.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time

log = logging.getLogger("memory.tunnel")
_want = {"id": ""}
_status = {"running": False, "url": None, "reason": "off"}
_wake = threading.Event()
_thread: threading.Thread | None = None
_proc: subprocess.Popen | None = None
MAX_BACKOFF = 120.0


def status() -> dict:
    return {"tunnel_id": _want["id"], "cli": bool(find_cli()), **_status}


def find_cli() -> str | None:
    found = shutil.which("devtunnel")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (rf"{local}\Microsoft\WinGet\Links\devtunnel.exe",
                    rf"{local}\Microsoft\WinGet\Packages\Microsoft.devtunnel_*\devtunnel.exe"):
        hits = glob.glob(pattern)
        if hits:
            return hits[0]
    return None


def start(tunnel_id: str) -> None:
    global _thread
    tunnel_id = (tunnel_id or "").strip()
    if not tunnel_id:
        stop()
        return
    changed = tunnel_id != _want["id"]
    _want["id"] = tunnel_id
    if changed:
        _kill()
    if not (_thread and _thread.is_alive()):
        _thread = threading.Thread(target=_supervise, name="memory-tunnel", daemon=True)
        _thread.start()
    _wake.set()


def stop() -> None:
    _want["id"] = ""
    _kill()
    _wake.set()
    _status.update(running=False, url=None, reason="off")


def _kill() -> None:
    global _proc
    p, _proc = _proc, None
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()


def _supervise() -> None:
    global _proc
    backoff = 0.0
    while _want["id"]:
        exe = find_cli()
        if not exe:
            _status.update(running=False, url=None, reason="the devtunnel command isn't installed (winget install Microsoft.devtunnel)")
            _wake.wait(60)
            _wake.clear()
            continue
        tunnel_id = _want["id"]
        started = time.monotonic()
        try:
            _proc = subprocess.Popen([exe, "host", tunnel_id], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
        except OSError as e:
            _status.update(running=False, url=None, reason=f"couldn't start devtunnel: {e}")
            _proc = None
        if _proc:
            _status.update(running=False, reason="connecting…")
            last_line = ""
            for line in _proc.stdout:  # ends when the process exits (or is killed)
                line = line.strip()
                if not line:
                    continue
                last_line = line
                m = re.search(r"https://\S+?\.devtunnels\.ms\b", line)
                if m and "-inspect" not in m.group(0) and line.lower().startswith("connect via browser"):
                    _status["url"] = m.group(0)
                if "Ready to accept connections" in line:
                    _status.update(running=True, reason="on")
                    log.info("tunnel %s is up at %s", tunnel_id, _status["url"])
                    backoff = 0.0
                lowered = line.lower()
                if "login" in lowered and ("required" in lowered or "expired" in lowered or "unauthorized" in lowered):
                    _status["reason"] = "sign in again: run devtunnel user login"
            code = _proc.wait() if _proc else None
            _proc = None
            if not _want["id"]:
                break
            reason = _status["reason"] if "sign in" in _status["reason"] else f"stopped ({last_line[:160] or f'exit code {code}'})"
            _status.update(running=False, reason=reason)
            log.warning("tunnel %s stopped: %s", tunnel_id, last_line[:200])
        if time.monotonic() - started > 300:
            backoff = 0.0  # it ran for a while: treat this as a fresh failure
        backoff = min(MAX_BACKOFF, backoff * 2 or 5.0)
        _status["reason"] = f"{_status['reason']}; retrying in {backoff:.0f} s"
        _wake.wait(backoff)
        _wake.clear()
    _status.update(running=False, url=None, reason="off")
