"""Light, monochrome desktop utility palette and native Tk styles."""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BACKGROUND = "#f8f8f9"
SURFACE = BACKGROUND
DIVIDER = "#e5e5e8"
ACCENT = "#171719"
ACCENT_SOFT = "#343438"
ACCENT_DARK = "#ffffff"
TEXT_PRIMARY = "#18181b"
TEXT_SECONDARY = "#52525b"
TEXT_MUTED = "#62626d"
LABEL_MUTED = TEXT_SECONDARY
HINT_MUTED = TEXT_MUTED
STATUS_DETAIL = TEXT_MUTED
HOTKEY_LABEL = TEXT_MUTED
COMBO_FIELD_BG = "#fcfcfd"
COMBO_ACTIVE_BG = "#ededf0"
COMBO_BORDER = "#d9d9de"
COMBO_DARK = COMBO_BORDER
BUTTON_BG = "#ededf0"
BUTTON_ACTIVE_BG = "#e2e2e6"
BUTTON_ACTIVE_FG = TEXT_PRIMARY
BUTTON_FG = TEXT_PRIMARY
CAPTURE_BG = ACCENT
CAPTURE_ACTIVE_BG = ACCENT_SOFT
CAPTURE_FG = "#ffffff"
SUCCESS = "#217a54"
ERROR = "#b42318"
OVERLAY_BG = "#fafafa"
OVERLAY_SHELL_BG = "#fafafa"
OVERLAY_SHELL_BORDER = "#d4d4d8"
OVERLAY_HINT = "#3f3f46"
OVERLAY_BAR_BRIGHT = "#18181b"

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else ("SF Pro Text" if sys.platform == "darwin" else "DejaVu Sans")
MONO_FAMILY = "Consolas" if sys.platform == "win32" else ("SF Mono" if sys.platform == "darwin" else "DejaVu Sans Mono")


def enable_light_titlebar(root: tk.Tk) -> None:
    """Keep the native Windows titlebar light, matching the dashboard."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(0)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def apply(root: tk.Tk) -> tkfont.Font:
    style = ttk.Style(root)
    style.theme_use("clam")
    popup_font = tkfont.Font(root, family=FONT_FAMILY, size=9)
    root.option_add("*TCombobox*Listbox.background", COMBO_FIELD_BG)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", BUTTON_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.font", str(popup_font))
    style.configure(
        "Voxen.TCombobox", fieldbackground=COMBO_FIELD_BG, background=COMBO_FIELD_BG,
        foreground=TEXT_PRIMARY, arrowcolor=TEXT_SECONDARY, bordercolor=COMBO_BORDER,
        lightcolor=COMBO_BORDER, darkcolor=COMBO_BORDER, padding=(8, 7),
        arrowsize=12, font=(FONT_FAMILY, 9),
    )
    style.map(
        "Voxen.TCombobox",
        fieldbackground=[("disabled", BUTTON_BG), ("readonly", COMBO_FIELD_BG)],
        background=[("disabled", BUTTON_BG), ("active", COMBO_ACTIVE_BG), ("readonly", COMBO_FIELD_BG)],
        foreground=[("disabled", TEXT_MUTED), ("readonly", TEXT_PRIMARY)],
        arrowcolor=[("disabled", TEXT_MUTED), ("readonly", TEXT_SECONDARY)],
        selectbackground=[("readonly", BUTTON_BG)], selectforeground=[("readonly", TEXT_PRIMARY)],
        bordercolor=[("focus", TEXT_SECONDARY)],
    )
    for name in ("Voxen.TButton", "Voxen.TMenubutton"):
        style.configure(name, background=COMBO_FIELD_BG, foreground=TEXT_PRIMARY,
                        bordercolor=COMBO_BORDER, lightcolor=COMBO_BORDER, darkcolor=COMBO_BORDER,
                        padding=(9, 7), font=(FONT_FAMILY, 9), relief="flat")
        style.map(name, background=[("pressed", BUTTON_ACTIVE_BG), ("active", BUTTON_BG)],
                  bordercolor=[("focus", TEXT_SECONDARY)])
    return popup_font
