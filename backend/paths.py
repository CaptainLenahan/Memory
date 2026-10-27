"""Where Memory's code, web files and data live, whether it runs from source or as the installed app.

From source, data stays in ./data next to the code (as before). The installed app (a PyInstaller bundle) keeps data in
%LOCALAPPDATA%\\Memory, so updating or uninstalling the program never touches your tasks. MEMORY_DATA_DIR overrides both.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
CODE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))  # bundled files when frozen
INSTALL_DIR = Path(sys.executable).resolve().parent if FROZEN else CODE_ROOT
FRONTEND = CODE_ROOT / "frontend"


def _default_data_dir() -> Path:
    if FROZEN:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Memory"
    return CODE_ROOT / "data"


DATA_DIR = Path(os.environ.get("MEMORY_DATA_DIR") or _default_data_dir())
ENV_FILE = (DATA_DIR if FROZEN else CODE_ROOT) / ".env"
