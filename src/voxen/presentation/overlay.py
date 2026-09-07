"""The floating recording pill — a minimal, borderless overlay.

Modeled after the compact floating "listening" indicator used by dictation
tools like Whispr Flow: a small rounded pill near the bottom of the screen
with a waveform and nothing else, instead of a bordered window with a
header, a hint line, and a status label. On Windows the corners are true
transparency (via ``-transparentcolor``) rather than a colored rectangle
behind a rounded shape, so the pill floats over the desktop with no visible
window edge; on platforms without that attribute it falls back to a plain
filled rounded rectangle on an opaque backdrop.
"""

from __future__ import annotations

import math
import sys
import tkinter as tk
from collections.abc import Callable

from . import theme
from .shapes import rounded_rect

_WIDTH = 320
_HEIGHT = 64
_RADIUS = _HEIGHT / 2 - 1
_BAR_COUNT = 22
_BOTTOM_MARGIN = 56
_TRANSPARENT_KEY = "#ff00fe"  # reserved colorkey, never used elsewhere in the palette

_MODE_ACCENT = {
    "listening": theme.ACCENT,
    "processing": theme.ACCENT_SOFT,
}


class RecordingOverlay:
    def __init__(self, root: tk.Tk, level_provider: Callable[[], float]) -> None:
        self._root = root
        self._level_provider = level_provider
        self._mode = "listening"
        self._phase = 0.0
        self._animation_id: str | None = None
        self._elapsed_text = "00:00"

        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)

        self._transparent = False
        if sys.platform == "win32":
            try:
                self._window.configure(bg=_TRANSPARENT_KEY)
                self._window.attributes("-transparentcolor", _TRANSPARENT_KEY)
                self._transparent = True
            except tk.TclError:
                self._transparent = False
        canvas_bg = _TRANSPARENT_KEY if self._transparent else theme.OVERLAY_BG
        if not self._transparent:
            self._window.configure(bg=theme.OVERLAY_BG)
        self._canvas = tk.Canvas(self._window, width=_WIDTH, height=_HEIGHT, bg=canvas_bg, highlightthickness=0)
        self._canvas.pack()

    def show(self, mode: str) -> None:
        self._mode = mode
        self._window.update_idletasks()
        x = max(0, (self._root.winfo_screenwidth() - _WIDTH) // 2)
        y = max(0, self._root.winfo_screenheight() - _HEIGHT - _BOTTOM_MARGIN)
        self._window.geometry(f"{_WIDTH}x{_HEIGHT}+{x}+{y}")
        self._window.deiconify()
        if self._animation_id is None:
            self._animate()

    def set_elapsed_seconds(self, seconds: int) -> None:
        self._elapsed_text = f"{seconds // 60:02d}:{seconds % 60:02d}"

    def hide(self) -> None:
        self._window.withdraw()
        if self._animation_id is not None:
            self._root.after_cancel(self._animation_id)
            self._animation_id = None

    def _animate(self) -> None:
        if not self._window.winfo_viewable():
            self._animation_id = None
            return
        canvas = self._canvas
        canvas.delete("all")
        rounded_rect(canvas, 1, 1, _WIDTH - 1, _HEIGHT - 1, _RADIUS, fill=theme.OVERLAY_SHELL_BG, outline=theme.OVERLAY_SHELL_BORDER, width=1)

        accent = _MODE_ACCENT[self._mode]
        center_y = _HEIGHT / 2
        dot_x, dot_r = 24, 4
        canvas.create_oval(dot_x - dot_r, center_y - dot_r, dot_x + dot_r, center_y + dot_r, fill=accent, outline="")

        bar_start = 42
        bar_area_width = _WIDTH - bar_start - 52
        step = bar_area_width / _BAR_COUNT
        for index in range(_BAR_COUNT):
            wave = abs(math.sin(self._phase + index * 0.55))
            if self._mode == "processing":
                height = 3 + wave * 6
            else:
                level = max(0.15, self._level_provider())
                height = 3 + wave * (5 + level * 15)
            x = bar_start + index * step
            color = accent if index % 4 else theme.OVERLAY_BAR_BRIGHT
            canvas.create_line(x, center_y - height / 2, x, center_y + height / 2, fill=color, width=2.4, capstyle="round")

        label = self._elapsed_text if self._mode == "listening" else "···"
        canvas.create_text(_WIDTH - 22, center_y, text=label, fill=theme.OVERLAY_HINT, font=(theme.MONO_FAMILY, 9), anchor="e")

        self._phase += 0.3
        self._animation_id = self._root.after(45, self._animate)
