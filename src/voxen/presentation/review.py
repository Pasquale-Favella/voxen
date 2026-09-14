"""Editable review pill for transcripts held in REVIEWING.

Kept deliberately small: a borderless-feel ``Toplevel`` with a ``Text``
editor, Confirm/Discard buttons and keyboard shortcuts. History browsing
lives in the dashboard; this window only edits the current draft.

The class is Tk-bound by nature, so unit tests cover ``DictationService``
instead — this module has no logic worth faking Tk for beyond construction.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from . import theme


class ReviewWindow:
    def __init__(
        self,
        root: tk.Tk | tk.Widget,
        *,
        on_confirm: Callable[[str], None],
        on_discard: Callable[[], None],
    ) -> None:
        self._on_confirm = on_confirm
        self._on_discard = on_discard
        self._visible = False

        self._window = tk.Toplevel(root)
        self._window.withdraw()
        self._window.overrideredirect(True)
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)
        self._window.configure(bg=theme.OVERLAY_SHELL_BG)

        frame = tk.Frame(self._window, bg=theme.OVERLAY_SHELL_BG, padx=14, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="Review draft — Ctrl+Enter to paste · Esc to discard",
            bg=theme.OVERLAY_SHELL_BG,
            fg=theme.OVERLAY_HINT,
            font=(theme.FONT_FAMILY, 8),
        ).pack(anchor="w", pady=(0, 8))

        self._text = tk.Text(
            frame,
            width=52,
            height=4,
            wrap="word",
            bg=theme.COMBO_FIELD_BG,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.ACCENT_SOFT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=theme.OVERLAY_SHELL_BORDER,
            font=(theme.FONT_FAMILY, 10),
        )
        self._text.pack(fill="both", expand=True)
        self._text.bind("<Control-Return>", lambda _e: self.confirm())
        self._text.bind("<Escape>", lambda _e: self.discard())

        buttons = tk.Frame(frame, bg=theme.OVERLAY_SHELL_BG)
        buttons.pack(fill="x", pady=(10, 0))
        tk.Button(
            buttons,
            text="Paste (Ctrl+Enter)",
            command=self.confirm,
            bg=theme.ACCENT,
            fg=theme.ACCENT_DARK,
            activebackground=theme.ACCENT_SOFT,
            relief="flat",
            padx=12,
            pady=6,
            font=(theme.FONT_FAMILY, 9, "bold"),
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Discard (Esc)",
            command=self.discard,
            bg=theme.BUTTON_BG,
            fg=theme.BUTTON_FG,
            activebackground=theme.BUTTON_ACTIVE_BG,
            relief="flat",
            padx=12,
            pady=6,
            font=(theme.FONT_FAMILY, 9),
        ).pack(side="left", padx=(8, 0))

    @property
    def visible(self) -> bool:
        return self._visible

    def _place(self) -> None:
        self._window.update_idletasks()
        width = max(self._window.winfo_reqwidth(), 420)
        height = max(self._window.winfo_reqheight(), 170)
        try:
            root = self._window.master
            cx = root.winfo_screenwidth() // 2
            bottom = root.winfo_screenheight() - 110
        except tk.TclError:
            cx, bottom = 960, 900
        x = max(0, cx - width // 2)
        y = max(0, bottom - height)
        self._window.geometry(f"{width}x{height}+{x}+{y}")

    def show(self, draft: str) -> None:
        self._text.delete("1.0", "end")
        self._text.insert("1.0", draft)
        self._place()
        self._window.deiconify()
        self._window.lift()
        self._visible = True
        try:
            self._text.focus_set()
        except tk.TclError:
            pass

    def hide(self) -> None:
        self._window.withdraw()
        self._visible = False

    def edited_text(self) -> str:
        return self._text.get("1.0", "end").strip()

    def confirm(self) -> None:
        self._on_confirm(self.edited_text())

    def discard(self) -> None:
        self._on_discard()
