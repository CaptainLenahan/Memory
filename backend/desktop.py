"""Open Memory as app-style windows on the Windows desktop.

The desktop wallpaper (Lively) can only pass mouse clicks through, so anything that needs typing, pasting or
file drops opens in a real window instead: Edge (or Chrome) in --app mode, which has no tabs or address bar.
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import db


def _browser() -> str | None:
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for p in (pf86 / "Microsoft/Edge/Application/msedge.exe", pf / "Microsoft/Edge/Application/msedge.exe",
              pf / "Google/Chrome/Application/chrome.exe", pf86 / "Google/Chrome/Application/chrome.exe",
              local / "Google/Chrome/Application/chrome.exe"):
        if p.is_file():
            return str(p)
    return shutil.which("msedge") or shutil.which("chrome")


def _work_area() -> tuple[int, int, int, int]:
    """Primary monitor's work area (excludes the taskbar), in the scaled pixels browsers use for window flags."""
    if sys.platform != "win32":
        return 0, 0, 1600, 900

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    r = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def open_window(url: str, kind: str = "popup") -> str:
    """Open url in a chromeless app window centred on screen; falls back to a normal browser tab."""
    exe = _browser()
    if not exe:
        webbrowser.open(url)
        return "tab"
    x0, y0, w, h = _work_area()
    if kind == "popup":
        ww, hh = min(1060, int(w * 0.82)), min(860, int(h * 0.9))
    else:
        ww, hh = int(w * 0.9), int(h * 0.9)
    x, y = x0 + (w - ww) // 2, y0 + (h - hh) // 2
    # A browser that's already running ignores size/position flags, so Memory's windows get their own profile
    # (and therefore their own browser instance) under data/.
    profile = db.DATA_DIR / "app-window-profile"
    # InPrivate: Edge doesn't sign these windows in to your account, so no sync prompts pop up over them
    subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--inprivate", "--no-first-run", "--no-default-browser-check",
                      f"--window-size={ww},{hh}", f"--window-position={x},{y}"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return "window"
