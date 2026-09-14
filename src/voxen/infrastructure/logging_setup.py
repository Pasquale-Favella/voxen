"""Rotating file logging, so failures in a packaged .exe are not invisible.

Before this module existed, the only logger in the whole codebase was
``audio.py``'s, and its one warning (a dropped audio block) had nowhere to
go: no handler was ever configured, so it was discarded by Python's default
"last resort" handler. In a windowed PyInstaller build there is no console
to print to either way, so every other ``except Exception: pass`` in the
codebase was, in effect, permanently silent.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3


def _log_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "Voxen"
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Voxen" / "logs"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")


def configure(level: int = logging.INFO) -> Path:
    """Attach a rotating file handler to the ``voxen`` logger tree; return its path."""
    log_dir = _log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "voxen.log"

    root_logger = logging.getLogger("voxen")
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        if isinstance(handler, RotatingFileHandler) and getattr(handler, "_voxen_log_path", None) == str(log_path):
            break
    else:
        handler = RotatingFileHandler(log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler._voxen_log_path = str(log_path)  # type: ignore[attr-defined]
        root_logger.addHandler(handler)
    if not _is_frozen():
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
                break
        else:
            stream = logging.StreamHandler()
            stream.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
            root_logger.addHandler(stream)
    return log_path
