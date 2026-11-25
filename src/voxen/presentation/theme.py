"""System appearance detection, immutable palettes and native Tk styles."""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

APPEARANCE_POLL_MS = 2000


@dataclass(frozen=True)
class Palette:
    name: str
    SURFACE: str
    DIVIDER: str
    ACCENT: str
    ACCENT_SOFT: str
    ACCENT_DARK: str
    TEXT_PRIMARY: str
    TEXT_SECONDARY: str
    TEXT_MUTED: str
    COMBO_FIELD_BG: str
    COMBO_ACTIVE_BG: str
    COMBO_BORDER: str
    BUTTON_BG: str
    BUTTON_ACTIVE_BG: str
    SUCCESS: str
    ERROR: str
    OVERLAY_SHELL_BG: str
    OVERLAY_SHELL_BORDER: str
    OVERLAY_HINT: str


LIGHT = Palette(
    "light", "#f8f8f9", "#e5e5e8", "#171719", "#343438", "#ffffff",
    "#18181b", "#52525b", "#62626d", "#fcfcfd", "#ededf0", "#d9d9de",
    "#ededf0", "#e2e2e6", "#217a54", "#b42318", "#fafafa", "#d4d4d8", "#3f3f46",
)
DARK = Palette(
    "dark", "#141416", "#29292d", "#ededee", "#d0d0d4", "#18181b",
    "#f1f1f3", "#a1a1aa", "#92929c", "#1b1b1e", "#242427", "#35353b",
    "#222225", "#2d2d31", "#71cba0", "#ff9893", "#19191c", "#38383e", "#c3c3ca",
)

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else ("SF Pro Text" if sys.platform == "darwin" else "DejaVu Sans")
MONO_FAMILY = "Consolas" if sys.platform == "win32" else ("SF Mono" if sys.platform == "darwin" else "DejaVu Sans Mono")


def read_system_appearance() -> str | None:
    """Read OS application appearance; return None if unavailable.

    No subprocess, network or additional dependency. macOS uses the existing
    Cocoa/PyObjC dependency; Windows reads AppsUseLightTheme (not taskbar theme).
    """
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return {0: "dark", 1: "light"}.get(value)
        if sys.platform == "darwin":
            from CoreFoundation import (
                CFPreferencesCopyValue,
                CFPreferencesSynchronize,
                kCFPreferencesAnyApplication,
                kCFPreferencesAnyHost,
                kCFPreferencesCurrentUser,
            )

            scope = (kCFPreferencesAnyApplication, kCFPreferencesCurrentUser, kCFPreferencesAnyHost)
            CFPreferencesSynchronize(*scope)
            value = CFPreferencesCopyValue("AppleInterfaceStyle", *scope)
            return "dark" if value == "Dark" else "light"
    except (ImportError, OSError, AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return None


def resolve_palette(preference: str, fallback: Palette = LIGHT) -> Palette:
    resolved = read_system_appearance() if preference == "system" else preference
    if resolved == "dark":
        return DARK
    if resolved == "light":
        return LIGHT
    return fallback


def apply_native_appearance(root: tk.Tk, preference: str, palette: Palette) -> None:
    """Match native titlebar/menu appearance when the OS supports it."""
    try:
        if sys.platform == "win32":
            import ctypes

            root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            value = ctypes.c_int(palette.name == "dark")
            for attribute in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
        elif sys.platform == "darwin":
            from AppKit import NSAppearance, NSApplication

            appearance = None if preference == "system" else NSAppearance.appearanceNamed_(
                "NSAppearanceNameDarkAqua" if palette.name == "dark" else "NSAppearanceNameAqua"
            )
            NSApplication.sharedApplication().setAppearance_(appearance)
    except Exception:
        # Native chrome is best effort; the application's palette remains usable.
        pass


def apply(root: tk.Tk, palette: Palette, popup_font: tkfont.Font | None = None) -> tkfont.Font:
    style = ttk.Style(root)
    style.theme_use("clam")
    if popup_font is None:
        popup_font = tkfont.Font(root, family=FONT_FAMILY, size=9)
    root.option_add("*TCombobox*Listbox.background", palette.COMBO_FIELD_BG)
    root.option_add("*TCombobox*Listbox.foreground", palette.TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.selectBackground", palette.BUTTON_BG)
    root.option_add("*TCombobox*Listbox.selectForeground", palette.TEXT_PRIMARY)
    root.option_add("*TCombobox*Listbox.font", str(popup_font))
    style.configure(
        "Voxen.TCombobox", fieldbackground=palette.COMBO_FIELD_BG, background=palette.COMBO_FIELD_BG,
        foreground=palette.TEXT_PRIMARY, arrowcolor=palette.TEXT_SECONDARY, bordercolor=palette.COMBO_BORDER,
        lightcolor=palette.COMBO_BORDER, darkcolor=palette.COMBO_BORDER, padding=(8, 7),
        arrowsize=12, font=(FONT_FAMILY, 9),
    )
    style.map(
        "Voxen.TCombobox",
        fieldbackground=[("disabled", palette.BUTTON_BG), ("readonly", palette.COMBO_FIELD_BG)],
        background=[("disabled", palette.BUTTON_BG), ("active", palette.COMBO_ACTIVE_BG), ("readonly", palette.COMBO_FIELD_BG)],
        foreground=[("disabled", palette.TEXT_MUTED), ("readonly", palette.TEXT_PRIMARY)],
        arrowcolor=[("disabled", palette.TEXT_MUTED), ("readonly", palette.TEXT_SECONDARY)],
        selectbackground=[("readonly", palette.BUTTON_BG)], selectforeground=[("readonly", palette.TEXT_PRIMARY)],
        bordercolor=[("focus", palette.TEXT_SECONDARY)],
    )
    for name in ("Voxen.TButton", "Voxen.TMenubutton"):
        style.configure(name, background=palette.COMBO_FIELD_BG, foreground=palette.TEXT_PRIMARY,
                        bordercolor=palette.COMBO_BORDER, lightcolor=palette.COMBO_BORDER, darkcolor=palette.COMBO_BORDER,
                        padding=(9, 7), font=(FONT_FAMILY, 9), relief="flat")
        style.map(name, background=[("pressed", palette.BUTTON_ACTIVE_BG), ("active", palette.BUTTON_BG)],
                  bordercolor=[("focus", palette.TEXT_SECONDARY)])
    return popup_font
