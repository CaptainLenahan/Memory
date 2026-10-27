"""Start Memory in the background with no console window (used by the Windows sign-in and Start menu shortcuts).

    pythonw launcher.pyw          start the server if it isn't already running
    pythonw launcher.pyw --open   ...and open Memory in the browser

Server output goes to data/server.log (rotated at 5 MB).
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

PORT = int(os.environ.get("MEMORY_PORT", "8765"))
URL = f"http://localhost:{PORT}"


def running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def open_when_ready() -> None:
    for _ in range(120):
        if running():
            webbrowser.open(URL)
            return
        time.sleep(0.5)


def main() -> None:
    want_open = "--open" in sys.argv
    if running():
        if want_open:
            webbrowser.open(URL)
        return

    data = Path(os.environ.get("MEMORY_DATA_DIR", ROOT / "data"))
    data.mkdir(parents=True, exist_ok=True)
    log_path = data / "server.log"
    if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
        log_path.replace(log_path.with_suffix(".log.1"))
    # pythonw has no console; send all output to the log so uvicorn's handlers have somewhere to write.
    sys.stdout = sys.stderr = open(log_path, "a", buffering=1, encoding="utf-8")
    print(f"\n--- Memory starting {time.strftime('%Y-%m-%d %H:%M:%S')} on {URL} ---")

    if want_open:
        threading.Thread(target=open_when_ready, daemon=True).start()
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=PORT, access_log=False)


if __name__ == "__main__":
    main()
