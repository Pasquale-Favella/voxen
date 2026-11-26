"""Non-recording runtime smoke check for the installed desktop package."""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch


def check_runtime() -> None:
    import onnxruntime
    import pyperclip
    import sounddevice
    from onnx_asr.loader import Manager

    from voxen import app as app_module
    from voxen.config import ConfigStore

    if sys.platform != "darwin":
        import pyautogui
        from pynput import keyboard

        assert callable(pyautogui.hotkey)
        assert callable(keyboard.Listener)

    assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
    assert callable(Manager.create_asr)
    assert callable(pyperclip.copy)
    assert callable(sounddevice.query_devices)
    # Keep the model stub active for the full worker lifetime, not just construction.
    with (
        tempfile.TemporaryDirectory(prefix="voxen-runtime-") as directory,
        patch.object(app_module, "ConfigStore", lambda: ConfigStore(Path(directory) / "config.json")),
        patch.object(app_module.ModelManager, "warm", return_value=None) as warm,
    ):
        root = tk.Tk()
        app = app_module.VoxenApp(root, start_services=sys.platform == "darwin")
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
            check_reopen(root, app, Path(directory))
            if sys.platform == "darwin":
                # A barrier on the actual serial model executor ensures warm-up
                # completed before draining the ready event. No sleeps or network.
                app.dictation._executor.submit(lambda: None).result(timeout=10)
                app._drain_events()
                warm.assert_called_once()
                check_macos_services(app)
        finally:
            app.close()
    print("Voxen runtime check passed (UI, native libraries and input backends).")
    wav = os.environ.get("VOXEN_PARAKEET_TEST_WAV")
    expected = os.environ.get("VOXEN_PARAKEET_TEST_EXPECTED")
    if wav or expected:
        if not wav or not expected:
            raise RuntimeError("Both speech fixture and expected transcript are required.")
        check_inference(Path(wav), expected)


def check_inference(wav: Path, expected: str) -> None:
    """Test the actual bundled runtime and pinned model, including offline reload."""
    import wave

    import numpy as np

    from voxen.stt import ParakeetEngine

    with wave.open(str(wav), "rb") as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, 16_000)
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype(np.float32) / 32768.0

    with tempfile.TemporaryDirectory(prefix="voxen-smoke-models-") as directory:
        cache = Path(directory)
        engine = ParakeetEngine(cache_root=cache)
        try:
            engine.load()
            assert engine._vad_enabled, "Silero VAD failed to load"
            first = engine.transcribe(audio)
            assert expected.casefold() in first.casefold(), "Expected phrase missing from real inference"
        finally:
            engine.unload()
        offline = ParakeetEngine(cache_root=cache, offline=True)
        with patch("voxen.stt.urlopen", side_effect=AssertionError("Unexpected offline download")):
            try:
                offline.load()
                assert offline._vad_enabled
                assert offline.transcribe(audio) == first
            finally:
                offline.unload()
    print("Voxen real Parakeet inference and offline reload passed.")


def check_macos_services(app) -> None:
    """Exercise actual native callbacks without posting input to the host."""
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    import Quartz as q

    from voxen.domain.hotkey_combo import KeyCombination
    from voxen.infrastructure.macos_input import MacHotkey, MacPasteAutomation, key_name
    from voxen.infrastructure.macos_tray import MacTray

    assert app.tray is not None and isinstance(app.tray._icon, MacTray), "Native tray did not start"
    assert app.tray._icon.item is not None
    assert app.state.name == "READY"
    assert app.hotkey is not None or not q.CGPreflightListenEventAccess(), app._hotkey_error
    if app.hotkey is None:
        assert app._hotkey_error and "Input Monitoring" in app._hotkey_error
        print("Native event tap: Input Monitoring denied (expected on restricted CI).")
    else:
        assert isinstance(app.hotkey._listener, MacHotkey)
        assert app.hotkey._listener.tap is not None
        print("Native event tap: active.")
    events = []
    listener = MacHotkey(KeyCombination.parse("cmd+shift+space"), lambda: events.append("down"), lambda: events.append("up"))
    for down in (True, True, False):
        event = q.CGEventCreateKeyboardEvent(None, 49, down)
        q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand | q.kCGEventFlagMaskShift)
        listener.callback(None, q.kCGEventKeyDown if down else q.kCGEventKeyUp, event, None)
    assert events == ["down", "up"]
    # Exercise the actual PyObjC Unicode bridge (no event is posted globally).
    letter = q.CGEventCreateKeyboardEvent(None, 0, True)
    q.CGEventKeyboardSetUnicodeString(letter, 1, "z")
    assert key_name(q, letter, 0) == "z"
    # Build real Quartz paste events on the existing delivery thread boundary,
    # but intercept posting so the CI host's active application is untouched.
    posted = []
    quartz = SimpleNamespace(
        CGPreflightPostEventAccess=lambda: True,
        CGEventCreateKeyboardEvent=q.CGEventCreateKeyboardEvent,
        CGEventSetFlags=q.CGEventSetFlags,
        CGEventPost=lambda _, event: posted.append(event),
        kCGEventFlagMaskCommand=q.kCGEventFlagMaskCommand,
        kCGHIDEventTap=q.kCGHIDEventTap,
    )
    with ThreadPoolExecutor(max_workers=1) as worker:
        worker.submit(MacPasteAutomation(quartz).hotkey, "command", "v").result(timeout=5)
    assert [q.CGEventGetType(event) for event in posted] == [q.kCGEventKeyDown, q.kCGEventKeyUp]
    assert all(q.CGEventGetFlags(event) & q.kCGEventFlagMaskCommand for event in posted)
    print("macOS native services startup, synthetic Quartz callbacks and delivery worker passed.")


def check_reopen(root, app, directory: Path) -> None:
    """Validate dashboard restoration on the same Tk instance."""
    from voxen.infrastructure.single_instance import InstanceGate, install_activation_handler

    with InstanceGate(directory / "instance") as gate:
        assert gate.start_or_activate()
        app._hide_settings()
        root.update()
        (directory / "instance" / "reopen").touch()
        cancel = install_activation_handler(root, gate, app._show_settings)
        try:
            root.update()
            assert root.state() == "normal", "Activation did not restore the original window"
            assert not (directory / "instance" / "reopen").exists()
        finally:
            cancel()
    if sys.platform == "darwin":
        app._hide_settings()
        root.update()
        root.tk.call("::tk::mac::ReopenApplication")
        root.update()
        assert root.state() == "normal", "Native reopen did not restore the dashboard"
    print("Voxen single-instance dashboard activation passed.")
