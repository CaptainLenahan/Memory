"""Computer specs and live usage for the desktop overlay, using only Windows APIs (no extra packages).

specs(): static facts, read once. usage(): the latest sample from a background sampler that runs every few seconds
while someone is asking (it stops itself after a minute without requests, so an idle Memory costs nothing).
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import socket
import sys
import threading
import time
from ctypes import wintypes

WINDOWS = sys.platform == "win32"
SAMPLE_EVERY = 2.0
IDLE_STOP = 60.0

_lock = threading.Lock()
_latest: dict = {}
_last_request = 0.0
_thread: threading.Thread | None = None
_specs: dict | None = None


# ---------- static specs ----------

def _reg(path: str, name: str) -> str | None:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
            return str(winreg.QueryValueEx(k, name)[0]).strip()
    except OSError:
        return None


def _gpus() -> list[str]:
    names: list[str] = []
    try:
        import winreg
        base = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                sub = winreg.EnumKey(k, i)
                if not sub.isdigit():
                    continue
                desc = _reg(f"{base}\\{sub}", "DriverDesc")
                if desc and desc not in names and "Basic Display" not in desc and "Virtual" not in desc:
                    names.append(desc)
    except OSError:
        pass
    return names


class _MEMSTATUS(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def _memory() -> tuple[int, int]:
    m = _MEMSTATUS()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys, m.ullTotalPhys - m.ullAvailPhys


def _system_drive() -> str:
    return (os.environ.get("SystemDrive", "C:") + "\\") if WINDOWS else "/"


def specs() -> dict:
    global _specs
    if _specs is not None:
        return _specs
    if not WINDOWS:
        _specs = {"host": socket.gethostname(), "os": platform.platform(), "cpu": platform.processor(), "threads": os.cpu_count()}
        return _specs
    cv = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    build = int(_reg(cv, "CurrentBuildNumber") or 0)
    product = (_reg(cv, "ProductName") or "Windows").replace("Windows 10", "Windows 11" if build >= 22000 else "Windows 10")
    drive = _system_drive()
    _specs = {
        "host": socket.gethostname(),
        "os": f"{product} {_reg(cv, 'DisplayVersion') or ''} (build {build})".replace("  ", " "),
        "cpu": " ".join((_reg(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString") or platform.processor()).split()),
        "threads": os.cpu_count(),
        "gpus": _gpus(),
        "ram_total": _memory()[0],
        "disk": drive.rstrip("\\"),
        "disk_total": shutil.disk_usage(drive).total,
    }
    return _specs


# ---------- live usage ----------

class _PdhValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _PdhItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PdhValue)]


class _Pdh:
    """A few performance counters (wildcard instances allowed), read as {instance: value}."""
    PDH_FMT_DOUBLE = 0x00000200
    PDH_MORE_DATA = 0x800007D2

    def __init__(self, paths: dict[str, str]):
        self.pdh = ctypes.WinDLL("pdh")
        self.query = ctypes.c_void_p()
        self.pdh.PdhOpenQueryW(None, None, ctypes.byref(self.query))
        self.counters = {}
        for key, path in paths.items():
            c = ctypes.c_void_p()
            if self.pdh.PdhAddEnglishCounterW(self.query, path, None, ctypes.byref(c)) == 0:
                self.counters[key] = c
        self.pdh.PdhCollectQueryData(self.query)

    def read(self) -> dict[str, dict[str, float]]:
        self.pdh.PdhCollectQueryData(self.query)
        out = {}
        for key, c in self.counters.items():
            size, count = wintypes.DWORD(0), wintypes.DWORD(0)
            rc = self.pdh.PdhGetFormattedCounterArrayW(c, self.PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
            if rc & 0xFFFFFFFF != self.PDH_MORE_DATA or not size.value:
                continue
            buf = ctypes.create_string_buffer(size.value)
            if self.pdh.PdhGetFormattedCounterArrayW(c, self.PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf) != 0:
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_PdhItem))
            out[key] = {items[i].szName: items[i].FmtValue.doubleValue for i in range(count.value) if items[i].FmtValue.CStatus in (0, 1)}
        return out


def _gpu_percent(engines: dict[str, float]) -> float | None:
    """Task Manager's figure: per engine, add up every process's share; report the busiest engine."""
    if not engines:
        return None
    per_engine: dict[str, float] = {}
    for name, v in engines.items():
        key = name.split("_luid_", 1)[-1]  # drop the "pid_1234" prefix: luid_..._phys_0_eng_0_engtype_3D
        per_engine[key] = per_engine.get(key, 0.0) + v
    return round(min(100.0, max(per_engine.values())), 1)


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]


def _battery() -> dict | None:
    s = _SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.BatteryFlag & 128 or s.BatteryLifePercent > 100:
        return None  # no battery (desktop) or unknown
    return {"percent": s.BatteryLifePercent, "charging": s.ACLineStatus == 1}


def _sampler() -> None:
    pdh = _Pdh({
        "cpu": r"\Processor(_Total)\% Processor Time",
        "gpu": r"\GPU Engine(*)\Utilization Percentage",
        "disk": r"\PhysicalDisk(_Total)\% Disk Time",
        "net_in": r"\Network Interface(*)\Bytes Received/sec",
        "net_out": r"\Network Interface(*)\Bytes Sent/sec",
    })
    drive = _system_drive()
    while time.monotonic() - _last_request < IDLE_STOP:
        time.sleep(SAMPLE_EVERY)
        try:
            v = pdh.read()
            total, used = _memory()
            du = shutil.disk_usage(drive)
            sample = {
                "cpu": round(min(100.0, next(iter(v.get("cpu", {}).values()), 0.0)), 1),
                "gpu": _gpu_percent(v.get("gpu", {})),
                "ram_used": used, "ram_total": total,
                "disk_used": du.used, "disk_total": du.total,
                "disk_active": round(min(100.0, next(iter(v.get("disk", {}).values()), 0.0)), 1),
                "net_in": round(sum(v.get("net_in", {}).values())), "net_out": round(sum(v.get("net_out", {}).values())),
                "uptime": ctypes.windll.kernel32.GetTickCount64() // 1000,
                "battery": _battery(),
                "at": time.time(),
            }
            with _lock:
                _latest.clear()
                _latest.update(sample)
        except Exception:  # never let a counter hiccup kill the sampler
            pass


def usage() -> dict:
    """Latest sample (empty until the sampler's first tick). Starts the sampler if it isn't running."""
    global _last_request, _thread
    _last_request = time.monotonic()
    if WINDOWS and (_thread is None or not _thread.is_alive()):
        _ctypes_setup()
        _thread = threading.Thread(target=_sampler, name="memory-sysinfo", daemon=True)
        _thread.start()
    with _lock:
        return dict(_latest)


def _ctypes_setup() -> None:
    k32 = ctypes.windll.kernel32
    k32.GetTickCount64.restype = ctypes.c_ulonglong
