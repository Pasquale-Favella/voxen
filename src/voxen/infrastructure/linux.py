"""Linux desktop and XDG helpers."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def xdg_directory(variable: str, default: str) -> Path:
    path = Path(os.environ.get(variable, ""))
    return path if path.is_absolute() else Path.home() / default


def require_x11() -> None:
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or os.environ.get("WAYLAND_DISPLAY") or not os.environ.get("DISPLAY"):
        raise SystemExit("Voxen requires a Linux X11 session for global dictation. Log in using Xorg; native Wayland is not supported yet.")


def host_environment() -> dict[str, str]:
    env = dict(os.environ)
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)
    return env


def read_portal_appearance() -> str | None:
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return None
    try:
        result = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop", "--method", "org.freedesktop.portal.Settings.Read",
             "org.freedesktop.appearance", "color-scheme"],
            capture_output=True, text=True, timeout=0.25, check=True, env=host_environment(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"uint32\s+([012])\b", result.stdout)
    return {"1": "dark", "2": "light"}.get(match.group(1)) if match else None
