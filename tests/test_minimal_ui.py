"""Exercise the actual Tk layout without starting audio or downloading models."""

import tkinter as tk

import pytest

from voxen import app as app_module
from voxen.config import ConfigStore
from voxen.presentation import overlay as ov


@pytest.fixture
def dashboard(monkeypatch, tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable; run with xvfb-run on Linux")
    root.withdraw()
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
