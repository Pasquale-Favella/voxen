"""Non-recording runtime smoke check for the installed desktop package."""
from __future__ import annotations

import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch


def check_runtime() -> None:
    import onnxruntime
    import pyautogui
    import pyperclip
    import sounddevice
    from onnx_asr.loader import Manager
    from pynput import keyboard

    from voxen import app as app_module
    from voxen.config import ConfigStore

    assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
    assert callable(Manager.create_asr)
    assert callable(pyautogui.hotkey)
    assert callable(pyperclip.copy)
    assert callable(sounddevice.query_devices)
    assert callable(keyboard.Listener)
    with tempfile.TemporaryDirectory(prefix="voxen-runtime-") as directory:
        root = tk.Tk()
        with patch.object(app_module, "ConfigStore", lambda: ConfigStore(Path(directory) / "config.json")):
            app = app_module.VoxenApp(root, start_services=False)
        try:
            root.deiconify()
            root.update()
            assert app.model_combo.get() == "Parakeet v3"
            assert app.brand_mark.cget("image")
            app.appearance_menu.invoke(2)
            assert app.palette.name == "dark"
            app.overlay.show("listening")
            root.update()
            assert app.overlay._window.winfo_viewable()
            app.overlay.hide()
        finally:
            app.close()
    print("Voxen runtime check passed (UI, native libraries and input backends).")
