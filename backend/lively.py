"""Use Lively Wallpaper for the desktop brain, started by Memory so the order is always right.

If Lively starts before Memory's server is listening, its wallpaper page fails to load and stays blank. So with
"Start Lively with Memory" on, Memory:
- turns off Lively's own start-at-sign-in entry (it would race ahead of the server),
- starts Lively a few seconds after its own server is up, if it isn't running,
- and if Lively is already running and set to Memory's wallpaper but no wallpaper page has connected within
  ~25 s (it loaded too early and is showing an error), restarts Lively once so it loads the page again.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("memory.lively")
_started_at = time.monotonic()
_wallpaper_seen = 0.0
_status = {"installed": False, "running": False, "reason": "off"}


def note_wallpaper_client() -> None:
    """A wallpaper page (Lively's or the built-in one) opened its live connection to Memory."""
    global _wallpaper_seen
    _wallpaper_seen = time.monotonic()


def find() -> str | None:
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            exe = Path(base) / "Lively Wallpaper" / "Lively.exe"
            if exe.is_file():
                return str(exe)
    return None


def running() -> bool:
    from .wallpaper import lively_running
    return lively_running()


def shows_memory(port: int) -> bool:
    """Is Lively's current wallpaper Memory's page?"""
    data = Path(os.environ.get("LOCALAPPDATA", "")) / "Lively Wallpaper"
    try:
        layout = json.loads((data / "WallpaperLayout.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for entry in layout if isinstance(layout, list) else []:
        info = Path(entry.get("LivelyInfoPath") or "") / "LivelyInfo.json"
        try:
            target = json.loads(info.read_text(encoding="utf-8-sig")).get("FileName", "")
        except (OSError, ValueError):
            continue
        if f"localhost:{port}" in target and "wallpaper" in target:
            return True
    return False


def disable_own_autostart() -> bool:
    """Remove Lively's sign-in entry (Memory starts it instead). Returns True if one was removed."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "Lively")
        log.info("turned off Lively's own start-at-sign-in; Memory starts it instead")
        return True
    except OSError:
        return False


def _launch(exe: str) -> None:
    flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if sys.platform == "win32" else 0
    subprocess.Popen([exe], cwd=str(Path(exe).parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def _stop_lively() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "Lively.exe", "/IM", "Lively.UI.WinUI.exe", "/IM", "Lively.Player.WebView2.exe"],
                   capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def status() -> dict:
    return dict(_status, installed=bool(find()), running=running())


def ensure(port: int, delay: float = 3.0, recover_after: float = 25.0) -> None:
    """Start Lively once Memory is listening (in the background), and recover a page that loaded too early."""
    def run():
        time.sleep(delay)
        exe = find()
        if not exe:
            _status["reason"] = "Lively Wallpaper isn't installed (Microsoft Store or winget install rocksdanister.LivelyWallpaper)"
            return
        disable_own_autostart()
        if not running():
            log.info("starting Lively Wallpaper")
            _launch(exe)
            _status["reason"] = "started by Memory"
            return
        _status["reason"] = "already running"
        waited = time.monotonic() - _started_at
        time.sleep(max(0.0, recover_after - waited))
        if running() and shows_memory(port) and _wallpaper_seen < _started_at:
            log.info("Lively's Memory wallpaper never connected (it probably loaded before the server); restarting Lively")
            _stop_lively()
            time.sleep(2)
            _launch(exe)
            _status["reason"] = "restarted so the wallpaper could load"

    threading.Thread(target=run, name="memory-lively", daemon=True).start()
