"""Memory's entry point: run the server in the background with no window (pythonw / the packaged Memory.exe).

    Memory.exe                     start the server if it isn't already running
    Memory.exe --open              ...and open Memory in the browser
    Memory.exe --install-startup   start Memory at sign-in (Task Scheduler) and keep it running
    Memory.exe --remove-startup    undo that
    Memory.exe --version

Server output goes to <data>/server.log (rotated at 5 MB).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _port() -> int:
    return int(os.environ.get("MEMORY_PORT", "8765"))


def running(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _open_when_ready(port: int) -> None:
    for _ in range(120):
        if running(port):
            webbrowser.open(f"http://localhost:{port}")
            return
        time.sleep(0.5)


def _message(text: str, title: str = "Memory") -> None:
    """Windowless builds have no console: show results of --install-startup etc. in a message box."""
    if sys.stdout and getattr(sys.stdout, "isatty", lambda: False)():
        print(text)
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    from . import paths
    from .version import __version__

    try:
        from dotenv import load_dotenv
        load_dotenv(paths.ENV_FILE)
    except ImportError:
        pass
    port = _port()

    if "--version" in argv:
        _message(f"Memory {__version__}")
        return
    if "--install-startup" in argv or "--remove-startup" in argv:
        from . import startup
        result = startup.remove() if "--remove-startup" in argv else startup.install()
        if "--quiet" not in argv:
            _message({"task": "Memory will start when you sign in (Task Scheduler task “Memory”).",
                      "shortcut": "Memory will start when you sign in (Startup folder shortcut).",
                      "removed": "Memory will no longer start when you sign in."}.get(result, f"Couldn't change startup: {result}"))
        return

    want_open = "--open" in argv
    if running(port):
        if want_open:
            webbrowser.open(f"http://localhost:{port}")
        return

    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_path = paths.DATA_DIR / "server.log"
    if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
        log_path.replace(log_path.with_suffix(".log.1"))
    # no console: send all output to the log so uvicorn's handlers have somewhere to write
    sys.stdout = sys.stderr = open(log_path, "a", buffering=1, encoding="utf-8")
    print(f"\n--- Memory {__version__} starting {time.strftime('%Y-%m-%d %H:%M:%S')} on http://localhost:{port} ---")

    import logging
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    memory_log = logging.getLogger("memory")
    memory_log.addHandler(handler)
    memory_log.setLevel(logging.INFO)

    if want_open:
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    import uvicorn

    from .app import app
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
