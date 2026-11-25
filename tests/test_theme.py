"""Platform appearance resolution without requiring the native OS."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from voxen.presentation import theme


def test_explicit_appearance_does_not_read_system(monkeypatch):
    def fail():
        raise AssertionError("System appearance should not be read")

    monkeypatch.setattr(theme, "read_system_appearance", fail)
    assert theme.resolve_palette("dark") == theme.DARK
    assert theme.resolve_palette("light") == theme.LIGHT


def test_system_fallback_preserves_previous_palette(monkeypatch):
    monkeypatch.setattr(theme, "read_system_appearance", lambda: None)
    assert theme.resolve_palette("system") == theme.LIGHT
    assert theme.resolve_palette("system", theme.DARK) == theme.DARK


def test_windows_uses_application_theme(monkeypatch):
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, OpenKey=MagicMock(), QueryValueEx=MagicMock(return_value=(0, 4)))
    monkeypatch.setattr(theme.sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "winreg", registry)
    assert theme.read_system_appearance() == "dark"
    registry.QueryValueEx.assert_called_once()
    assert registry.QueryValueEx.call_args.args[1] == "AppsUseLightTheme"
    registry.QueryValueEx.return_value = (1, 4)
    assert theme.read_system_appearance() == "light"


def test_macos_reads_global_appearance(monkeypatch):
    preferences = SimpleNamespace(
        CFPreferencesCopyValue=MagicMock(return_value="Dark"), CFPreferencesSynchronize=MagicMock(),
        kCFPreferencesAnyApplication="global", kCFPreferencesCurrentUser="user", kCFPreferencesAnyHost="host",
    )
    monkeypatch.setattr(theme.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "CoreFoundation", preferences)
    assert theme.read_system_appearance() == "dark"
    preferences.CFPreferencesSynchronize.assert_called_once_with("global", "user", "host")
    preferences.CFPreferencesCopyValue.return_value = None
    assert theme.read_system_appearance() == "light"
