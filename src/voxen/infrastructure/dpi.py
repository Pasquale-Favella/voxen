"""Process DPI awareness on Windows.

The overlay is positioned with raw Win32 metrics (``GetMonitorInfoW``),
which Windows *virtualizes* while the process is DPI-unaware: coordinates
come back divided by the system scale factor (e.g. ``/1.25`` at 125%
scaling), and the unaware window itself gets bitmap-scaled up. If anything
flips the process to aware later on, every target rect jumps by that factor
from one showing to the next — the pill looks slightly bigger on the first
dictation, then bounces to the new position on later ones.

Declaring per-monitor V2 awareness once, before any window exists, keeps
metrics physical from the first map on. Best-effort: awareness can only be
set once per process, and older Windows builds lack the newer APIs, so
every step degrades gracefully to leaving the process default.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Win10 1703+).
_V2_CONTEXT = -4
# PROCESS_PER_MONITOR_DPI_AWARE (Win8.1+, Shcore.h).
_PER_MONITOR_AWARE = 2
# S_OK: SetProcessDpiAwareness reports success as an HRESULT, unlike the
# BOOL returned by the other two calls.
_S_OK = 0


def ensure_awareness() -> str | None:
    """Declare per-monitor DPI awareness; return the mode set, if any."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        windll = ctypes.windll
    except (ImportError, AttributeError):
        logger.debug("DPI awareness unavailable: no windll")
        return None
    try:
        if windll.user32.SetProcessDpiAwarenessContext(_V2_CONTEXT):
            logger.debug("DPI awareness: per-monitor V2")
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        if windll.shcore.SetProcessDpiAwareness(_PER_MONITOR_AWARE) == _S_OK:
            logger.debug("DPI awareness: per-monitor (shcore)")
            return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        if windll.user32.SetProcessDPIAware():
            logger.debug("DPI awareness: system")
            return "system"
    except (AttributeError, OSError):
        pass
    logger.debug("DPI awareness could not be set; leaving process default")
    return None
