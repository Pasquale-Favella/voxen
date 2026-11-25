"""Exercise the actual Tk layout without starting audio or downloading models."""

import tkinter as tk

import pytest

from voxen import app as app_module
from voxen.config import ConfigStore
from voxen.presentation import overlay as ov
from voxen.presentation import theme


@pytest.fixture
def dashboard(monkeypatch, tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable; run with xvfb-run on Linux")
    root.withdraw()
    monkeypatch.setattr(theme, "read_system_appearance", lambda: "light")
    monkeypatch.setattr(app_module, "ConfigStore", lambda: ConfigStore(tmp_path / "config.json"))
    monkeypatch.setattr(app_module.VoxenApp, "_start_services", lambda self: None)
    app = app_module.VoxenApp(root)
    try:
        root.deiconify()
        root.update()
        yield app
    finally:
        app.close()


def test_minimal_dashboard_preserves_controls(dashboard):
    app = dashboard
    assert app.model_combo.get() == "Parakeet v3"
    assert app.language_combo.get() == "Auto"
    assert app.language_combo.instate(["disabled"])
    assert app.save_button.winfo_ismapped()
    assert app.root.winfo_height() < 460
    app.model_combo.current(1)
    app.model_combo.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert app.model_var.get() == "base"
    assert app.language_combo.instate(["readonly"])
    app.language_combo.current(2)
    app.language_combo.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert app.language_var.get() == "en"
    app.preferences_menu.invoke(0)
    assert app.auto_paste_var.get() is False


def test_pill_has_compact_geometry_and_distinct_processing_state(dashboard):
    overlay = dashboard.overlay
    overlay.show("listening")
    dashboard.root.update()
    assert (overlay._canvas.winfo_width(), overlay._canvas.winfo_height()) == (ov._WIDTH, ov._HEIGHT)
    assert overlay._canvas.itemcget(overlay._label_id, "text") == "00:00"
    overlay.show("processing")
    overlay._animate()
    assert overlay._canvas.itemcget(overlay._label_id, "text") == "···"
    overlay.hide()



def test_dark_appearance_applies_to_open_widgets_and_persists(dashboard):
    app = dashboard
    app.overlay.show("listening")
    app.root.update()
    app.overlay.set_elapsed_seconds(7)
    light_brand = str(app._brand_photo)
    app.appearance_menu.invoke(2)
    assert str(app._brand_photo) != light_brand
    assert app.brand_mark.cget("image") == str(app._brand_photo)
    assert app.config.appearance == "dark"
    assert app.store.load().appearance == "dark"
    assert app.palette == theme.DARK
    assert app.root.cget("background") == theme.DARK.SURFACE
    assert app.overlay._canvas.cget("background") == theme.DARK.OVERLAY_SHELL_BG
    assert app.overlay._elapsed_text == "00:07"
    app.overlay.hide()
    app.appearance_menu.invoke(1)
    assert app.palette == theme.LIGHT
    assert app.store.load().appearance == "light"


def test_follow_system_updates_without_saving_or_resetting_preferences(dashboard, monkeypatch):
    app = dashboard
    app.auto_paste_var.set(False)
    monkeypatch.setattr(theme, "read_system_appearance", lambda: "dark")
    app.root.after_cancel(app._theme_poll_id)
    app._poll_system_appearance()
    assert app.palette == theme.DARK
    assert app.config.appearance == "system"
    assert app.auto_paste_var.get() is False
    app.appearance_menu.invoke(1)
    app.root.after_cancel(app._theme_poll_id)
    app._poll_system_appearance()
    assert app.palette == theme.LIGHT
    assert app.store.load().auto_paste is True
