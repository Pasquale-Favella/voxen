"""The floating recording pill — a minimal, borderless overlay.

Modeled after the compact floating "listening" indicator used by dictation
tools like Whispr Flow: a small rounded pill near the bottom of the screen
with a waveform and nothing else, instead of a bordered window with a
header, a hint line, and a status label. On Windows the corners are true
window clipping (via a native rounded region) rather than a color-key
transparency pass, so the pill stays stable while floating over the desktop;
on platforms without native clipping it falls back to a plain filled rounded
rectangle on an opaque backdrop.
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
_BOTTOM_MARGIN = 16

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
        self._visual_level = 0.0
        self._bar_heights = [3.0] * _BAR_COUNT
        self._animation_id: str | None = None
        self._elapsed_text = "00:00"
        self._visible = False

        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)

        self._native_region = False
        if sys.platform == "win32":
            try:
                self._window.configure(bg=theme.OVERLAY_SHELL_BG)
                self._native_region = True
            except tk.TclError:
                self._native_region = False
        canvas_bg = theme.OVERLAY_SHELL_BG if self._native_region else theme.OVERLAY_BG
        if not self._native_region:
            self._window.configure(bg=theme.OVERLAY_BG)
        self._canvas = tk.Canvas(self._window, width=_WIDTH, height=_HEIGHT, bg=canvas_bg, highlightthickness=0)
        self._canvas.pack()
        self._build_canvas_items()

        # The first time this window is actually mapped, Windows pays a
        # one-time cost (DWM surface/region setup, DPI context binding for
        # whichever monitor it lands on) that shows up as the pill briefly
        # flashing at the wrong size/position before settling. Paying that
        # cost once at startup — at the real target position, shown and
        # hidden again before the user can register it — means the first
        # real recording behaves exactly like every later one.
        self._root.after(60, self._warm_up)

    def _warm_up(self) -> None:
        if self._visible:
            return
        try:
            self._position_window()
            self._window.deiconify()
            self._window.update()
            self._window.withdraw()
        except tk.TclError:
            pass

    def _build_canvas_items(self) -> None:
        canvas = self._canvas
        rounded_rect(
            canvas,
            1,
            1,
            _WIDTH - 1,
            _HEIGHT - 1,
            _RADIUS,
            fill=theme.OVERLAY_SHELL_BG,
            outline=theme.OVERLAY_SHELL_BORDER,
            width=1,
        )
        center_y = _HEIGHT / 2
        dot_x, dot_r = 24, 4
        self._dot_id = canvas.create_oval(dot_x - dot_r, center_y - dot_r, dot_x + dot_r, center_y + dot_r, outline="")

        bar_start = 42
        step = (_WIDTH - bar_start - 52) / _BAR_COUNT
        self._bar_ids = [
            canvas.create_line(bar_start + index * step, center_y, bar_start + index * step, center_y, width=2.6, capstyle="round")
            for index in range(_BAR_COUNT)
        ]
        self._label_id = canvas.create_text(
            _WIDTH - 22,
            center_y,
            fill=theme.OVERLAY_HINT,
            font=(theme.MONO_FAMILY, 9),
            anchor="e",
        )

    def show(self, mode: str) -> None:
        self._mode = mode
        if not self._visible:
            self._position_window()
            self._window.deiconify()
            self._visible = True
        if self._animation_id is None:
            self._animate()

    def _position_window(self) -> None:
        work_left, work_top, work_right, work_bottom = self._monitor_work_area()
        x = work_left + max(0, (work_right - work_left - _WIDTH) // 2)
        y = work_bottom - _HEIGHT - _BOTTOM_MARGIN
        self._window.geometry(f"{_WIDTH}x{_HEIGHT}+{x}+{y}")
        self._window.update_idletasks()
        self._apply_native_region()

    def _apply_native_region(self) -> None:
        if not self._native_region:
            return
        try:
            import ctypes

            width = max(1, self._window.winfo_width())
            height = max(1, self._window.winfo_height())
            radius = min(width, height)
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
            if region and not ctypes.windll.user32.SetWindowRgn(self._window.winfo_id(), region, True):
                ctypes.windll.gdi32.DeleteObject(region)
        except (AttributeError, OSError, tk.TclError):
            self._native_region = False

    def _monitor_work_area(self) -> tuple[int, int, int, int]:
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes

                class Rect(ctypes.Structure):
                    _fields_ = (("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG))

                class MonitorInfo(ctypes.Structure):
                    _fields_ = (("size", wintypes.DWORD), ("monitor", Rect), ("work", Rect), ("flags", wintypes.DWORD))

                monitor = ctypes.windll.user32.MonitorFromWindow(self._root.winfo_id(), 2)
                info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
                if monitor and ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    return info.work.left, info.work.top, info.work.right, info.work.bottom
            except (AttributeError, OSError, tk.TclError):
                pass
        return (
            self._root.winfo_vrootx(),
            self._root.winfo_vrooty(),
            self._root.winfo_vrootx() + self._root.winfo_screenwidth(),
            self._root.winfo_vrooty() + self._root.winfo_screenheight(),
        )

    def set_elapsed_seconds(self, seconds: int) -> None:
        self._elapsed_text = f"{seconds // 60:02d}:{seconds % 60:02d}"

    def hide(self) -> None:
        self._window.withdraw()
        self._visible = False
        if self._animation_id is not None:
            self._root.after_cancel(self._animation_id)
            self._animation_id = None

    def _animate(self) -> None:
        if not self._window.winfo_viewable():
            self._animation_id = None
            return
        canvas = self._canvas

        accent = _MODE_ACCENT[self._mode]
        canvas.itemconfigure(self._dot_id, fill=accent)
        center_y = _HEIGHT / 2

        bar_start = 42
        bar_area_width = _WIDTH - bar_start - 52
        step = bar_area_width / _BAR_COUNT
        raw_level = max(0.0, min(1.0, float(self._level_provider())))
        self._visual_level += (raw_level - self._visual_level) * 0.38
        for index in range(_BAR_COUNT):
            if self._mode == "processing":
                target_height = 3 + abs(math.sin(self._phase + index * 0.55)) * 6
            else:
                position = index / (_BAR_COUNT - 1)
                envelope = 0.58 + 0.42 * math.sin(math.pi * position)
                ripple = 0.55 + 0.45 * abs(math.sin(self._phase * 1.7 - index * 0.38))
                target_height = 3 + envelope * (2.5 + self._visual_level * (19 + 9 * ripple))
            response = 0.42 if target_height > self._bar_heights[index] else 0.18
            self._bar_heights[index] += (target_height - self._bar_heights[index]) * response
            height = self._bar_heights[index]
            x = bar_start + index * step
            color = theme.OVERLAY_BAR_BRIGHT if height > 13 else accent
            canvas.coords(self._bar_ids[index], x, center_y - height / 2, x, center_y + height / 2)
            canvas.itemconfigure(self._bar_ids[index], fill=color)

        label = self._elapsed_text if self._mode == "listening" else "···"
        canvas.itemconfigure(self._label_id, text=label)

        self._phase += 0.3
        self._animation_id = self._root.after(45, self._animate)
