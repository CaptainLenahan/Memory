"""Start Memory in the background with no console window. See backend/launcher.py for the options:

    pythonw launcher.pyw          start the server if it isn't already running
    pythonw launcher.pyw --open   ...and open Memory in the browser

This is also the entry point PyInstaller builds Memory.exe from (scripts/build.ps1).
"""
import os
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

from backend.launcher import main  # noqa: E402

if __name__ == "__main__":
    main()
