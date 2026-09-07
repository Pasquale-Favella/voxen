"""Canvas drawing helpers for the flat, rounded-pill look.

Stock ``tk.Button``/``tk.Frame`` can't have rounded corners, so anything
meant to read as a "pill" (the hotkey button, the save button, the
recording overlay) is drawn on a ``Canvas`` instead, using the classic
smoothed-polygon trick for the rounded rectangle.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs) -> int:
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
        x1 + radius, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class RoundedButton(tk.Canvas):
    """A pill-shaped clickable button. Supports the subset of ``tk.Button``
    behavior the app needs: click, focus, and rebinding key events (for
    hotkey capture) — but colors go through ``set_colors`` rather than
    ``configure``, since a ``Canvas`` has no ``fg``/``activebackground``."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        command: Callable[[], None] | None = None,
        text: str | None = None,
        textvariable: tk.StringVar | None = None,
        bg: str,
        fg: str,
        active_bg: str,
        parent_bg: str,
        width: int = 180,
        height: int = 40,
        font: tuple = ("Segoe UI", 10, "bold"),
    ) -> None:
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0)
        self._command = command
        self._text = text or ""
        self._textvariable = textvariable
        self._bg = bg
        self._fg = fg
        self._active_bg = active_bg
        self._font = font
        self._hover = False
        if textvariable is not None:
            textvariable.trace_add("write", lambda *_: self._redraw())
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._redraw()

    def _label(self) -> str:
        return self._textvariable.get() if self._textvariable is not None else self._text

    def _on_enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._redraw()

    def _on_click(self, _event: tk.Event) -> None:
        self.focus_set()
        if self._command is not None:
            self._command()

    def set_colors(self, *, bg: str, fg: str, active_bg: str) -> None:
        self._bg = bg
        self._fg = fg
        self._active_bg = active_bg
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width, height = int(self["width"]), int(self["height"])
        fill = self._active_bg if self._hover else self._bg
        rounded_rect(self, 1, 1, width - 1, height - 1, height / 2, fill=fill, outline="")
        self.create_text(width / 2, height / 2, text=self._label(), fill=self._fg, font=self._font)


class Checkbox(tk.Canvas):
    """A flat checkbox: a small rounded square plus a label, drawn on a
    Canvas. ttk's "clam" theme renders an unchecked box as a solid light
    square and a checked one as a light "X" glyph on a dark box — both read
    as broken against a near-black background, and neither is themeable
    through public ttk style options without an image-based element."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        variable: tk.BooleanVar,
        accent: str,
        text_fg: str,
        box_off_bg: str,
        box_border: str,
        check_fg: str,
        parent_bg: str,
        font: tuple = ("Segoe UI", 9),
        box_size: int = 16,
        gap: int = 8,
        height: int = 22,
    ) -> None:
        super().__init__(parent, height=height, bg=parent_bg, highlightthickness=0)
        self._text = text
        self._variable = variable
        self._accent = accent
        self._text_fg = text_fg
        self._box_off_bg = box_off_bg
        self._box_border = box_border
        self._check_fg = check_fg
        self._font = font
        self._box_size = box_size
        self._gap = gap
        self._height = height
        variable.trace_add("write", lambda *_: self._redraw())
        self.bind("<Button-1>", self._toggle)
        self._redraw()

    def _toggle(self, _event: tk.Event) -> None:
        self._variable.set(not self._variable.get())

    def _redraw(self) -> None:
        self.delete("all")
        center_y = self._height / 2
        box_y1 = center_y - self._box_size / 2
        box_y2 = center_y + self._box_size / 2
        checked = bool(self._variable.get())
        fill = self._accent if checked else self._box_off_bg
        outline = "" if checked else self._box_border
        rounded_rect(self, 0, box_y1, self._box_size, box_y2, 4, fill=fill, outline=outline, width=1.2)
        if checked:
            self.create_line(
                3, center_y,
                self._box_size * 0.42, box_y2 - 3,
                self._box_size - 3, box_y1 + 3,
                fill=self._check_fg, width=1.8, capstyle="round", joinstyle="round",
            )
        text_x = self._box_size + self._gap
        text_id = self.create_text(text_x, center_y, text=self._text, fill=self._text_fg, font=self._font, anchor="w")
        bbox = self.bbox(text_id)
        self.configure(width=(bbox[2] + 2) if bbox else text_x + 60)
