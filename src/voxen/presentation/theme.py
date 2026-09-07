"""Voxen's color palette and ttk style setup.

Pulled out of ``app.py`` so color literals scattered across widget
constructors live in one place; changing the palette no longer means
hunting through layout code.

The palette is a flat, near-black neutral scheme with a single mint-green
accent (matching the app's mark) and hairline dividers instead of boxed
"cards" — closer to the minimal, pill-shaped aesthetic of dictation tools
like Whispr Flow than Voxen's earlier boxed dark-green look.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BACKGROUND = "#0b0b0d"
SURFACE = "#0b0b0d"
DIVIDER = "#1e1e23"
ACCENT = "#489a7c"
ACCENT_SOFT = "#72e0ae"
ACCENT_DARK = "#ffffff"
TEXT_PRIMARY = "#f5f5f7"
TEXT_SECONDARY = "#8e8e96"
TEXT_MUTED = "#5b5b63"
LABEL_MUTED = "#8e8e96"
HINT_MUTED = "#5b5b63"
STATUS_DETAIL = "#8e8e96"
HOTKEY_LABEL = "#6f6f78"
COMBO_FIELD_BG = "#151517"
COMBO_ACTIVE_BG = "#1c1c20"
COMBO_BORDER = "#2a2a30"
COMBO_DARK = "#0b0b0d"
BUTTON_BG = "#151517"
BUTTON_ACTIVE_BG = "#1c1c20"
BUTTON_ACTIVE_FG = "#ffffff"
BUTTON_FG = "#f5f5f7"
CAPTURE_BG = "#489a7c"
CAPTURE_ACTIVE_BG = "#57ab8a"
CAPTURE_FG = "#ffffff"
OVERLAY_BG = "#0b0b0d"
OVERLAY_SHELL_BG = "#16161a"
OVERLAY_SHELL_BORDER = "#26262c"
OVERLAY_HINT = "#8e8e96"
OVERLAY_BAR_BRIGHT = "#b9f8d6"

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Consolas"


def enable_dark_titlebar(root: tk.Tk) -> None:
    """Best-effort: ask DWM to draw the native title bar in dark mode on Windows.

    A white Windows title bar sitting directly above a near-black body reads
    as broken, not "dark themed" — this is the standard ctypes trick to fix
    that on Windows 10 2004+/11. It is inherently best-effort: older Windows
    builds don't support the attribute, so failures are swallowed.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # 20 on Windows 10 20H1+/11, 19 on earlier builds
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
            if result == 0:
                break
    except Exception:
        pass


def apply(root: tk.Tk) -> tkfont.Font:
    """Configure ttk styles for this root and return the combobox popup font."""
    style = ttk.Style()
    style.theme_use("clam")
    combo_popup_font = tkfont.Font(root, family=FONT_FAMILY, size=10)
    root.option_add("*TCombobox*Listbox.background", COMBO_FIELD_BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_DARK)
    root.option_add("*TCombobox*Listbox.font", str(combo_popup_font))
    style.configure(
        "Voxen.TCombobox",
        fieldbackground=COMBO_FIELD_BG,
        background=COMBO_FIELD_BG,
        foreground=TEXT_PRIMARY,
        arrowcolor=ACCENT,
        bordercolor=COMBO_BORDER,
        lightcolor=COMBO_BORDER,
        darkcolor=COMBO_DARK,
        padding=(10, 7),
        arrowsize=15,
        font=(FONT_FAMILY, 10),
    )
    style.map(
        "Voxen.TCombobox",
        fieldbackground=[("readonly", COMBO_FIELD_BG), ("active", COMBO_ACTIVE_BG)],
        background=[("readonly", COMBO_FIELD_BG), ("active", COMBO_ACTIVE_BG), ("!disabled", COMBO_FIELD_BG)],
        foreground=[("readonly", TEXT_PRIMARY)],
        selectbackground=[("readonly", ACCENT)],
        selectforeground=[("readonly", ACCENT_DARK)],
        arrowcolor=[("readonly", ACCENT), ("active", ACCENT_SOFT)],
    )
    return combo_popup_font
