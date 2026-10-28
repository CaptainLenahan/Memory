"""Built-in desktop wallpaper: the brain behind your desktop icons, on each screen, without Lively.

How it works (Windows only, plain Win32 through ctypes):
- One borderless Edge window per screen shows /?wallpaper&screen=N, using its own small profile in the data folder.
- Each window is re-parented into the desktop layer: between the icons (SHELLDLL_DefView) and the Windows
  wallpaper (WorkerW). Both the newer "raised desktop" layout (Windows 11 24H2+) and the classic one are handled.
- The desktop eats mouse input, so a low-level mouse hook forwards moves, left clicks and the wheel over the bare
  desktop to the window underneath. A drag that starts on the desktop keeps forwarding until the button is released.
- A watcher pauses a screen's brain while a maximised or full-screen window covers it.
- A supervisor keeps it alive while the setting is on: it (re)builds the wallpaper whenever it's missing (sign-in
  before Edge or Explorer are ready, Explorer restarts, a window closing, screens added/removed/rearranged, waking
  from sleep), retrying with a growing delay, and steps aside while Lively Wallpaper runs, coming back when it exits.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

from . import desktop
from .paths import DATA_DIR
from .reminders import bus

log = logging.getLogger("memory.wallpaper")
WINDOWS = sys.platform == "win32"

_lock = threading.Lock()
_status = {"running": False, "screens": 0, "reason": "off"}
_want = {"on": False, "port": 8765, "screens": "all", "rebuild": False}
_wake = threading.Event()
_supervisor: threading.Thread | None = None
CHECK_EVERY = 4.0
MAX_BACKOFF = 60.0


def status() -> dict:
    return dict(_status)


def start(port: int, screens: str = "all") -> None:
    """Turn the wallpaper on (or apply new options). Returns at once; the supervisor does the work."""
    global _supervisor
    if not WINDOWS:
        _status.update(running=False, reason="Windows only")
        return
    with _lock:
        changed = _want["on"] and (_want["port"], _want["screens"]) != (port, screens)
        _want.update(on=True, port=port, screens=screens, rebuild=_want["rebuild"] or changed)
        if not (_supervisor and _supervisor.is_alive()):
            _supervisor = threading.Thread(target=_supervise, name="memory-wallpaper-supervisor", daemon=True)
            _supervisor.start()
    _wake.set()


def restart() -> None:
    _want["rebuild"] = True
    _wake.set()


def stop(wait: bool = True) -> None:
    with _lock:
        _want["on"] = False
        sup = _supervisor
    _wake.set()
    if wait and sup and sup is not threading.current_thread():
        sup.join(timeout=8)
    _status.update(running=False, screens=0, reason="off", covered=[])


def _supervise() -> None:
    host: _Host | None = None
    backoff, next_try = 0.0, 0.0
    try:
        while _want["on"]:
            if _want["rebuild"]:
                _want["rebuild"] = False
                if host:
                    host.stop()
                    host = None
                backoff, next_try = 0.0, 0.0
            if lively_running():
                if host:
                    log.info("Lively Wallpaper is running: stepping aside")
                    host.stop()
                    host = None
                _status.update(running=False, screens=0, reason="Lively Wallpaper is running, so Memory leaves the desktop "
                               "to it (Memory takes over again when Lively closes)", covered=[])
            elif not (host and host.healthy()):
                if host:
                    log.info("wallpaper needs rebuilding (%s)", host.problem or "stopped")
                    host.stop()
                    host = None
                if time.monotonic() >= next_try:
                    host = _Host(_want["port"], _want["screens"])
                    if host.start_and_wait():
                        backoff = 0.0
                    else:
                        backoff = min(MAX_BACKOFF, backoff * 2 or 5.0)
                        next_try = time.monotonic() + backoff
                        log.warning("wallpaper didn't start (%s); retrying in %.0f s", _status.get("reason"), backoff)
                        _status["reason"] = f"{_status.get('reason')}; retrying in {backoff:.0f} s"
                        host.stop()
                        host = None
            _wake.wait(CHECK_EVERY)
            _wake.clear()
    except Exception:
        log.exception("wallpaper supervisor crashed")
    finally:
        if host:
            host.stop()
        _status.update(running=False, screens=0, covered=[])


def lively_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Lively.exe", "/NH"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return "Lively.exe" in out
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------- Win32 plumbing ----------------
if WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateRectRgn.restype = ctypes.c_void_p
    gdi32.CreateRectRgn.argtypes = [ctypes.c_int] * 4
    HWND, LPARAM, WPARAM = wintypes.HWND, wintypes.LPARAM, wintypes.WPARAM
    LRESULT = ctypes.c_ssize_t

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
    ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, HWND, LPARAM)
    MONPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), LPARAM)

    for name, res, args in [
        ("FindWindowW", HWND, [wintypes.LPCWSTR, wintypes.LPCWSTR]),
        ("FindWindowExW", HWND, [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]),
        ("SendMessageTimeoutW", LRESULT, [HWND, wintypes.UINT, WPARAM, LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]),
        ("EnumWindows", wintypes.BOOL, [ENUMPROC, LPARAM]),
        ("EnumChildWindows", wintypes.BOOL, [HWND, ENUMPROC, LPARAM]),
        ("EnumDisplayMonitors", wintypes.BOOL, [wintypes.HDC, ctypes.c_void_p, MONPROC, LPARAM]),
        ("GetClassNameW", ctypes.c_int, [HWND, wintypes.LPWSTR, ctypes.c_int]),
        ("GetWindowTextW", ctypes.c_int, [HWND, wintypes.LPWSTR, ctypes.c_int]),
        ("GetWindowLongPtrW", ctypes.c_ssize_t, [HWND, ctypes.c_int]),
        ("SetWindowLongPtrW", ctypes.c_ssize_t, [HWND, ctypes.c_int, ctypes.c_ssize_t]),
        ("SetParent", HWND, [HWND, HWND]),
        ("GetParent", HWND, [HWND]),
        ("SetWindowPos", wintypes.BOOL, [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]),
        ("MapWindowPoints", ctypes.c_int, [HWND, HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]),
        ("ScreenToClient", wintypes.BOOL, [HWND, ctypes.POINTER(wintypes.POINT)]),
        ("WindowFromPoint", HWND, [wintypes.POINT]),
        ("PostMessageW", wintypes.BOOL, [HWND, wintypes.UINT, WPARAM, LPARAM]),
        ("SetWindowsHookExW", ctypes.c_void_p, [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]),
        ("CallNextHookEx", LRESULT, [ctypes.c_void_p, ctypes.c_int, WPARAM, LPARAM]),
        ("UnhookWindowsHookEx", wintypes.BOOL, [ctypes.c_void_p]),
        ("GetMessageW", wintypes.BOOL, [ctypes.POINTER(wintypes.MSG), HWND, wintypes.UINT, wintypes.UINT]),
        ("PostThreadMessageW", wintypes.BOOL, [wintypes.DWORD, wintypes.UINT, WPARAM, LPARAM]),
        ("GetForegroundWindow", HWND, []),
        ("IsZoomed", wintypes.BOOL, [HWND]),
        ("IsWindow", wintypes.BOOL, [HWND]),
        ("IsWindowVisible", wintypes.BOOL, [HWND]),
        ("GetWindowRect", wintypes.BOOL, [HWND, ctypes.POINTER(wintypes.RECT)]),
        ("ShowWindow", wintypes.BOOL, [HWND, ctypes.c_int]),
        ("SetThreadDpiAwarenessContext", ctypes.c_void_p, [ctypes.c_void_p]),
        ("SetWindowRgn", ctypes.c_int, [HWND, ctypes.c_void_p, wintypes.BOOL]),
        ("GetWindow", HWND, [HWND, wintypes.UINT]),
        ("GetWindowThreadProcessId", wintypes.DWORD, [HWND, ctypes.POINTER(wintypes.DWORD)]),
    ]:
        f = getattr(user32, name)
        f.restype, f.argtypes = res, args

    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL, WM_CLOSE, WM_QUIT = 0x200, 0x201, 0x202, 0x20A, 0x10, 0x12
    MK_LBUTTON = 0x1
    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_CHILD, WS_POPUP, WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x40000000, 0x80000000, 0x00C00000, 0x00040000, 0x00080000
    WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
    WS_EX_TOOLWINDOW, WS_EX_APPWINDOW, WS_EX_NOACTIVATE = 0x80, 0x40000, 0x08000000
    SWP_NOACTIVATE, SWP_SHOWWINDOW, SWP_FRAMECHANGED = 0x10, 0x40, 0x20
    DESKTOP_CLASSES = {"SysListView32", "SHELLDLL_DefView", "WorkerW", "Progman"}


def _cls(h) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, b, 256)
    return b.value


def _title(h) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, b, 256)
    return b.value


def _rect(h) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def _monitors() -> list[tuple[int, int, int, int]]:
    """Screen rectangles, main screen first."""
    out: list[tuple[int, int, int, int]] = []
    cb = MONPROC(lambda m, dc, r, l: out.append((r.contents.left, r.contents.top, r.contents.right, r.contents.bottom)) or True)
    user32.EnumDisplayMonitors(None, None, cb, 0)
    return sorted(out, key=lambda r: (r[0] != 0 or r[1] != 0, r[0], r[1]))


def _desktop_layer() -> tuple:
    """(parent window for the wallpaper, window to sit just below or None, layout name)."""
    progman = user32.FindWindowW("Progman", None)
    res = ctypes.c_size_t()
    user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(res))  # ask Explorer to create the WorkerW
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(res))
    defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
    if defview:  # Windows 11 24H2+: icons and wallpaper are both children of Progman
        # Live inside the wallpaper layer (the WorkerW under the icons): Edge re-orders its own window now and then,
        # and inside WorkerW that can never lift it above the icons.
        workerw = user32.FindWindowExW(progman, None, "WorkerW", None)
        return (workerw, None, "raised") if workerw else (progman, defview, "raised")
    found = []

    def cb(h, _):
        if _cls(h) == "WorkerW" and user32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
            found.append(user32.FindWindowExW(None, h, "WorkerW", None))  # the WorkerW right after the icons' one
        return True
    user32.EnumWindows(ENUMPROC(cb), 0)
    return (found[0] if found and found[0] else progman), None, "classic"


def _find_window(title: str):
    """A wallpaper window by title, whether still top-level or already embedded in the desktop layer."""
    hits = []

    def cb(h, _):
        t = _title(h)  # Edge may add a suffix such as " - [InPrivate]"
        if _cls(h) == "Chrome_WidgetWin_1" and (t == title or t.startswith(title + " ")):
            hits.append(h)
        return True
    user32.EnumWindows(ENUMPROC(cb), 0)
    if not hits:
        parent, _, _ = _desktop_parent_only()
        if parent:
            user32.EnumChildWindows(parent, ENUMPROC(cb), 0)
    return hits[0] if hits else None


def _desktop_parent_only() -> tuple:
    """Where embedded wallpaper windows live, without asking Explorer to change anything."""
    progman = user32.FindWindowW("Progman", None)
    if user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None):
        return user32.FindWindowExW(progman, None, "WorkerW", None) or progman, None, "raised"
    found = []

    def cb(h, _):
        if _cls(h) == "WorkerW" and user32.FindWindowExW(h, None, "SHELLDLL_DefView", None):
            found.append(user32.FindWindowExW(None, h, "WorkerW", None))
        return True
    user32.EnumWindows(ENUMPROC(cb), 0)
    return (found[0] if found and found[0] else progman), None, "classic"


def _render_widget(top):
    hits = []

    def cb(h, _):
        if _cls(h) == "Chrome_RenderWidgetHostHWND":
            hits.append(h)
        return True
    user32.EnumChildWindows(top, ENUMPROC(cb), 0)
    return hits[0] if hits else top


class _Host:
    def __init__(self, port: int, screens: str):
        self.port, self.screens = port, screens
        self.windows: list[dict] = []        # {"hwnd", "render", "rect", "index"}
        self.thread: threading.Thread | None = None
        self.thread_id = 0
        self.stopping = threading.Event()
        self.left_down = False
        self.drag_target: dict | None = None
        self._hook = None
        self._hook_proc = None
        self._last_hwnd = None
        self._last_is_desktop = False
        self.parent = self.below = None
        self.monitors: list = []
        self.problem = ""
        self.attached = threading.Event()
        self.ok = False

    # ----- lifecycle -----
    def start_and_wait(self, timeout: float = 60) -> bool:
        """Build the wallpaper; True once every screen's window is in place."""
        self.thread = threading.Thread(target=self._run, name="memory-wallpaper", daemon=True)
        self.thread.start()
        self.attached.wait(timeout)
        return self.ok

    def healthy(self) -> bool:
        """Still running, every window still exists, and the screens haven't changed."""
        if not (self.thread and self.thread.is_alive() and self.ok):
            self.problem = "host stopped"
        elif not all(user32.IsWindow(w["hwnd"]) for w in self.windows):
            self.problem = "a wallpaper window closed (Explorer restart?)"
        elif self._screens() != self.monitors:
            self.problem = "screens changed"
        else:
            self.problem = ""
        return not self.problem

    def _screens(self) -> list:
        mons = _monitors()
        return mons[:1] if self.screens == "primary" else mons

    def stop(self) -> None:
        self.stopping.set()
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        if self.thread:
            self.thread.join(timeout=5)

    def _run(self) -> None:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor aware: real pixels everywhere
        self.thread_id = kernel32.GetCurrentThreadId()
        try:
            self.ok = self._attach()
            self.attached.set()
            if not self.ok:
                return
            self._hook_proc = HOOKPROC(self._on_mouse)
            self._hook = user32.SetWindowsHookExW(14, self._hook_proc, None, 0)  # WH_MOUSE_LL
            threading.Thread(target=self._watch, name="memory-wallpaper-watch", daemon=True).start()
            msg = wintypes.MSG()
            while not self.stopping.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        except Exception:
            log.exception("wallpaper host failed")
            _status.update(running=False, reason="failed to start (see server.log)")
        finally:
            self.attached.set()
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
            for w in self.windows:
                if user32.IsWindow(w["hwnd"]):
                    user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
            self.windows = []
            if self.stopping.is_set():
                _status.update(running=False, screens=0)

    def _attach(self) -> bool:
        exe = desktop._browser()
        if not exe:
            _status.update(running=False, reason="needs Microsoft Edge or Google Chrome")
            return False
        monitors = self.monitors = self._screens()
        parent, below, layout = _desktop_layer()
        self.parent, self.below = parent, below
        profile = DATA_DIR / "wallpaper-profile"
        for i, (l, t, r, b) in enumerate(monitors):
            title = f"Memory Wallpaper {i}"
            old = _find_window(title)
            if old:  # left over from a previous run
                user32.PostMessageW(old, WM_CLOSE, 0, 0)
                time.sleep(0.5)
            url = f"http://localhost:{self.port}/?wallpaper&screen={i}"
            # InPrivate: Edge never signs these windows in to your account, so no sync/sign-in prompts land on the
            # wallpaper (where nobody could click them)
            subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--inprivate", "--no-first-run", "--no-default-browser-check",
                              "--disable-features=CalculateNativeWinOcclusion", "--disable-backgrounding-occluded-windows",
                              "--disable-renderer-backgrounding", "--disable-background-timer-throttling", "--hide-crash-restore-bubble",
                              f"--window-position={l},{t}", f"--window-size={r - l},{b - t}"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            hwnd = None
            for _ in range(80):  # the page names its window once it has loaded
                hwnd = _find_window(title)
                if hwnd or self.stopping.is_set():
                    break
                time.sleep(0.25)
            if not hwnd:
                log.warning("wallpaper window %s did not appear", i)
                continue
            self._embed(hwnd, parent, below, (l, t, r, b))
            self.windows.append({"hwnd": hwnd, "render": _render_widget(hwnd), "rect": (l, t, r, b), "index": i})
        self._keep_below_icons()
        ok = len(self.windows) == len(monitors)  # all screens, or try again
        _status.update(running=ok, screens=len(self.windows), layout=layout,
                       reason="on" if ok else "the wallpaper window didn't open", covered=[])
        log.info("wallpaper on %d screen(s), %s desktop", len(self.windows), layout)
        return ok

    @staticmethod
    def _embed(hwnd, parent, below, rect) -> None:
        style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
        style &= ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style | WS_CHILD)
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        user32.SetParent(hwnd, parent)

        def place(l, t, r, b):
            pts = (wintypes.POINT * 2)(wintypes.POINT(l, t), wintypes.POINT(r, b))
            user32.MapWindowPoints(None, parent, pts, 2)  # screen -> parent client coordinates
            user32.SetWindowPos(hwnd, below or None, pts[0].x, pts[0].y, pts[1].x - pts[0].x, pts[1].y - pts[0].y,
                                SWP_NOACTIVATE | SWP_SHOWWINDOW | SWP_FRAMECHANGED | (0 if below else 0x4))  # 0x4: keep z-order

        L, T, R, B = rect
        place(L, T, R, B)
        # Edge draws its own title bar inside the window, so window styles can't remove it. Grow the window until the
        # page area itself covers the screen, then clip the window to that area so the title bar is never drawn.
        for _ in range(20):
            time.sleep(0.15)
            render = _render_widget(hwnd)
            if render == hwnd:
                continue
            wl, wt, wr, wb = _rect(hwnd)
            rl, rt, rr, rb = _rect(render)
            dl, dt, dr, db = rl - wl, rt - wt, wr - rr, wb - rb
            if (dl, dt, dr, db) == (0, 0, 0, 0) or rr - rl <= 0:
                break
            place(L - dl, T - dt, R + dr, B + db)
            user32.SetWindowRgn(hwnd, gdi32.CreateRectRgn(dl, dt, dl + (R - L), dt + (B - T)), True)
            break

    def _keep_below_icons(self) -> bool:
        """Edge sometimes raises its window; put every wallpaper window back just below the icons. Returns True if
        anything had drifted above them."""
        if not self.below:
            return False
        drifted, h = False, user32.GetWindow(self.parent, 5)  # GW_CHILD: top of the parent's z-order
        ours = {int(w["hwnd"] or 0) for w in self.windows}
        while h and h != self.below:
            if int(h or 0) in ours:
                drifted = True
            h = user32.GetWindow(h, 2)  # GW_HWNDNEXT
        if drifted:
            for w in self.windows:
                user32.SetWindowPos(w["hwnd"], self.below, 0, 0, 0, 0, 0x1 | 0x2 | SWP_NOACTIVATE)  # NOSIZE | NOMOVE
        return drifted

    def _close_strays(self) -> None:
        """Close any other window the wallpaper's Edge opens (a prompt or bubble): behind the icons nobody could click it."""
        pids = set()
        for w in self.windows:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(w["hwnd"], ctypes.byref(pid))
            pids.add(pid.value)
        ours = {int(w["hwnd"] or 0) for w in self.windows}

        def cb(h, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value in pids and int(h or 0) not in ours and user32.IsWindowVisible(h) and _cls(h).startswith("Chrome_WidgetWin"):
                log.info("closing a stray Edge window on the wallpaper: %r", _title(h))
                user32.PostMessageW(h, WM_CLOSE, 0, 0)
            return True
        user32.EnumWindows(ENUMPROC(cb), 0)

    # ----- mouse pass-through -----
    def _is_desktop(self, hwnd) -> bool:
        if hwnd == self._last_hwnd:
            return self._last_is_desktop
        h, ok = hwnd, False
        for _ in range(6):
            if not h:
                break
            if _cls(h) in DESKTOP_CLASSES or any(h == w["hwnd"] for w in self.windows):
                ok = True
                break
            h = user32.GetParent(h)
        self._last_hwnd, self._last_is_desktop = hwnd, ok
        return ok

    def _window_at(self, x: int, y: int):
        return next((w for w in self.windows if w["rect"][0] <= x < w["rect"][2] and w["rect"][1] <= y < w["rect"][3]), None)

    def _on_mouse(self, code, wparam, lparam):
        try:
            if code == 0 and wparam in (WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL):
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                self._forward(wparam, info)
        except Exception:  # never break the system mouse
            pass
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def _forward(self, msg, info) -> None:
        x, y = info.pt.x, info.pt.y
        target = self.drag_target if self.left_down else self._window_at(x, y)
        if not target:
            return
        if not self.left_down and not self._is_desktop(user32.WindowFromPoint(info.pt)):
            return  # the pointer is over some other window: leave it alone
        if not user32.IsWindow(target["render"]):
            target["render"] = _render_widget(target["hwnd"])
        render = target["render"]
        if msg == WM_MOUSEWHEEL:
            delta = ctypes.c_short(info.mouseData >> 16).value
            user32.PostMessageW(render, WM_MOUSEWHEEL, (delta & 0xFFFF) << 16, ((y & 0xFFFF) << 16) | (x & 0xFFFF))
            return
        p = wintypes.POINT(x, y)
        user32.ScreenToClient(render, ctypes.byref(p))
        lp = ((p.y & 0xFFFF) << 16) | (p.x & 0xFFFF)
        if msg == WM_LBUTTONDOWN:
            self.left_down, self.drag_target = True, target
            user32.PostMessageW(render, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        elif msg == WM_LBUTTONUP:
            if self.left_down:
                user32.PostMessageW(render, WM_LBUTTONUP, 0, lp)
            self.left_down, self.drag_target = False, None
        else:
            user32.PostMessageW(render, WM_MOUSEMOVE, MK_LBUTTON if self.left_down else 0, lp)

    # ----- pause when covered, give way to Lively, survive Explorer restarts -----
    def _watch(self) -> None:
        user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        covered_before: list[int] = []
        while not self.stopping.wait(1.5):
            if not all(user32.IsWindow(w["hwnd"]) for w in self.windows):
                return  # the supervisor notices and rebuilds
            self._keep_below_icons()
            self._close_strays()
            fg = user32.GetForegroundWindow()
            covered = []
            if fg and not self._is_desktop(fg) and user32.IsWindowVisible(fg):
                fl, ft, fr, fb = _rect(fg)
                zoomed = bool(user32.IsZoomed(fg))
                for w in self.windows:
                    l, t, r, b = w["rect"]
                    cx, cy = (fl + fr) // 2, (ft + fb) // 2
                    on_screen = l <= cx < r and t <= cy < b
                    fullscreen = fl <= l and ft <= t and fr >= r and fb >= b
                    if on_screen and (zoomed or fullscreen):
                        covered.append(w["index"])
            if covered != covered_before:
                covered_before = covered
                _status["covered"] = covered
                bus.publish("wallpaper", {"covered": covered})


def port_from_env() -> int:
    return int(os.environ.get("MEMORY_PORT", "8765"))
