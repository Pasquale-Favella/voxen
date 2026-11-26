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

import logging
import math
import sys
import tkinter as tk
from collections.abc import Callable

from . import theme
from .shapes import rounded_rect

logger = logging.getLogger(__name__)

_WIDTH = 240
_HEIGHT = 48
_RADIUS = _HEIGHT / 2 - 1
_BAR_COUNT = 15
_BOTTOM_MARGIN = 16
_MAX_HEALS = 3


class RecordingOverlay:
    def __init__(self, root: tk.Tk, level_provider: Callable[[], float], palette: theme.Palette = theme.LIGHT) -> None:
        self._root = root
        self._palette = palette
        self._level_provider = level_provider
        self._mode = "listening"
        self._phase = 0.0
        self._visual_level = 0.0
        self._bar_heights = [3.0] * _BAR_COUNT
        self._animation_id: str | None = None
        self._elapsed_text = "00:00"
        self._visible = False
        self._geometry: str | None = None
        self._applied_size: tuple[int, int] | None = None
        self._target: tuple[int, int, int, int] | None = None
        self._heals = 0

        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)

        self._window.configure(bg=self._palette.OVERLAY_SHELL_BG)
        self._native_region = sys.platform == "win32"
        self._canvas = tk.Canvas(self._window, width=_WIDTH, height=_HEIGHT, bg=self._palette.OVERLAY_SHELL_BG, highlightthickness=0)
        self._canvas.pack()
        self._build_canvas_items()
        try:
            self._window.bind("<Configure>", self._on_configure, add="+")
        except tk.TclError:
            pass

        # The first time this window is actually mapped, Windows pays a
        # one-time cost (DWM surface/region setup, DPI context binding for
        # whichever monitor it lands on) that showed up as the pill briefly
        # flashing at the wrong size/position before settling. Paying that
        # cost once at startup — at the real target position, shown and
        # hidden again before the user can register it — means the first
        # real recording behaves exactly like every later one. The warm-up
        # goes through the same map path as show(), and show() additionally
        # re-applies the native region *after* mapping plus once on the
        # next idle cycle, because winfo_width/height read before the first
        # map can disagree with the mapped size.
        self._root.after(60, self._warm_up)

    def _warm_up(self) -> None:
        if self._visible:
            return
        try:
            self._position_window()
            self._window.deiconify()
            self._window.update_idletasks()
            self._apply_native_region(force=True)
            self._window.update()
            self._window.withdraw()
        except tk.TclError:
            pass

    def _build_canvas_items(self) -> None:
        canvas = self._canvas
        self._shell_id = rounded_rect(
            canvas,
            1,
            1,
            _WIDTH - 1,
            _HEIGHT - 1,
            _RADIUS,
            fill=self._palette.OVERLAY_SHELL_BG,
            outline=self._palette.OVERLAY_SHELL_BORDER,
            width=1,
        )
        center_y = _HEIGHT / 2
        # Monochrome microphone glyph, drawn natively so it stays sharp at any DPI.
        x = 25
        canvas.create_oval(x - 15, center_y - 15, x + 15, center_y + 15, fill=self._palette.ACCENT, outline="", tags="mic_bg")
        rounded_rect(canvas, x - 3, center_y - 8, x + 3, center_y + 3, 3, fill=self._palette.ACCENT_DARK, outline="", tags="mic_fill")
        canvas.create_arc(x - 6, center_y - 5, x + 6, center_y + 7, start=180, extent=180,
                          style="arc", outline=self._palette.ACCENT_DARK, width=1.4, tags="mic_arc")
        canvas.create_line(x, center_y + 7, x, center_y + 10, fill=self._palette.ACCENT_DARK, width=1.4, tags="mic_fill")
        canvas.create_line(x - 4, center_y + 10, x + 4, center_y + 10, fill=self._palette.ACCENT_DARK, width=1.4, capstyle="round", tags="mic_fill")

        self._bar_ids = [
            canvas.create_line(self._bar_x(index), center_y, self._bar_x(index), center_y, width=2.2,
                               capstyle="round", fill=self._palette.ACCENT)
            for index in range(_BAR_COUNT)
        ]
        canvas.create_line(169, 13, 169, _HEIGHT - 13, fill=self._palette.DIVIDER, tags="divider")
        self._label_id = canvas.create_text(
            203, center_y, fill=self._palette.OVERLAY_HINT, font=(theme.MONO_FAMILY, 9),
        )

    def set_palette(self, palette: theme.Palette) -> None:
        self._palette = palette
        self._window.configure(bg=palette.OVERLAY_SHELL_BG)
        canvas = self._canvas
        canvas.configure(bg=palette.OVERLAY_SHELL_BG)
        canvas.itemconfigure(self._shell_id, fill=palette.OVERLAY_SHELL_BG, outline=palette.OVERLAY_SHELL_BORDER)
        canvas.itemconfigure("mic_bg", fill=palette.ACCENT)
        canvas.itemconfigure("mic_fill", fill=palette.ACCENT_DARK)
        canvas.itemconfigure("mic_arc", outline=palette.ACCENT_DARK)
        canvas.itemconfigure("divider", fill=palette.DIVIDER)
        canvas.itemconfigure(self._label_id, fill=palette.OVERLAY_HINT)
        for bar in self._bar_ids:
            canvas.itemconfigure(bar, fill=palette.ACCENT if self._mode == "listening" else palette.TEXT_MUTED)

    @staticmethod
    def _bar_x(index: int) -> float:
        return 49 + index * 7.5

    def show(self, mode: str) -> None:
        self._mode = mode
        if mode == "listening":
            self._elapsed_text = "00:00"
        if not self._visible:
            self._heals = 0
            self._position_window()
            self._window.deiconify()
            self._visible = True
            try:
                self._window.update_idletasks()
            except tk.TclError:
                pass
            self._apply_native_region(force=True)
            try:
                self._root.after_idle(self._reapply_after_map)
            except tk.TclError:
                pass
        if self._animation_id is None:
            self._animate()

    def _reapply_after_map(self) -> None:
        """Catch the window manager's post-map correction (DPI/shadow)."""
        if not self._visible:
            return
        self._heal_if_drifted()

    def _heal_if_drifted(self) -> None:
        """Snap back to the target rect if the manager moved/resized us.

        Deviation-triggered only, and bounded per show, so this can fix a
        first-map settle without ever fighting the window manager in a loop.
        """
        if not self._visible or self._target is None or self._heals >= _MAX_HEALS:
            return
        try:
            actual = (
                self._window.winfo_x(),
                self._window.winfo_y(),
                self._window.winfo_width(),
                self._window.winfo_height(),
            )
        except tk.TclError:
            return
        if actual == self._target:
            self._apply_native_region()
            return
        logger.debug("Overlay drifted: target=%s actual=%s; correcting", self._target, actual)
        # _position_window re-applies the region when the size changed;
        # a pure position drift needs no region refresh (it is size-based).
        self._position_window(force=True)
        self._heals += 1

    def _on_configure(self, _event) -> None:
        if not self._visible:
            return
        self._apply_native_region()

    def _position_window(self, *, force: bool = False) -> None:
        work_left, work_top, work_right, work_bottom = self._monitor_work_area()
        x = work_left + max(0, (work_right - work_left - _WIDTH) // 2)
        y = work_bottom - _HEIGHT - _BOTTOM_MARGIN
        self._target = (x, y, _WIDTH, _HEIGHT)
        geometry = f"{_WIDTH}x{_HEIGHT}+{x}+{y}"
        # Re-setting identical geometry can make the window manager
        # re-settle the window for a frame (perceived as a bounce), so only
        # move when the target actually changed (or healing forces it).
        if force or geometry != self._geometry:
            self._window.geometry(geometry)
            self._geometry = geometry
        self._window.update_idletasks()
        self._apply_native_region()

    def _apply_native_region(self, *, force: bool = False) -> None:
        if not self._native_region:
            return
        try:
            import ctypes

            width = max(1, self._window.winfo_width())
            height = max(1, self._window.winfo_height())
            if not force and (width, height) == self._applied_size:
                return
            radius = min(width, height)
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
            if not region:
                return
            if not ctypes.windll.user32.SetWindowRgn(self._window.winfo_id(), region, True):
                ctypes.windll.gdi32.DeleteObject(region)
                return
            self._applied_size = (width, height)
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
        left = self._root.winfo_vrootx()
        top = self._root.winfo_vrooty()
        # On macOS the top menu bar (~25px) is part of the full screen size;
        # keep the pill clear of it when no native work-area API is used.
        if sys.platform == "darwin":
            top += 25
        return (
            left,
            top,
            left + self._root.winfo_screenwidth(),
            top + self._root.winfo_screenheight(),
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
            # The first frame can run before the server maps the window;
            # retry instead of giving up, otherwise the pill would stay
            # frozen until the next show() (a visible jump on hotkey release).
            try:
                self._animation_id = self._root.after(45, self._animate)
            except tk.TclError:
                self._animation_id = None
            return
        self._heal_if_drifted()
        canvas = self._canvas

        accent = self._palette.ACCENT if self._mode == "listening" else self._palette.TEXT_MUTED
        center_y = _HEIGHT / 2

        raw_level = max(0.0, min(1.0, float(self._level_provider())))
        self._visual_level += (raw_level - self._visual_level) * 0.38
        for index in range(_BAR_COUNT):
            if self._mode == "processing":
                target_height = 3 + abs(math.sin(self._phase + index * 0.55)) * 6
            else:
                position = index / (_BAR_COUNT - 1)
                envelope = 0.58 + 0.42 * math.sin(math.pi * position)
                ripple = 0.55 + 0.45 * abs(math.sin(self._phase * 1.7 - index * 0.38))
                target_height = 2.5 + envelope * (1.5 + self._visual_level * (13 + 7 * ripple))
            response = 0.42 if target_height > self._bar_heights[index] else 0.18
            self._bar_heights[index] += (target_height - self._bar_heights[index]) * response
            height = self._bar_heights[index]
            x = self._bar_x(index)
            color = self._palette.TEXT_PRIMARY if height > 13 else accent
            canvas.coords(self._bar_ids[index], x, center_y - height / 2, x, center_y + height / 2)
            canvas.itemconfigure(self._bar_ids[index], fill=color)

        label = self._elapsed_text if self._mode == "listening" else "···"
        canvas.itemconfigure(self._label_id, text=label)

        self._phase += 0.3
        self._animation_id = self._root.after(45, self._animate)
