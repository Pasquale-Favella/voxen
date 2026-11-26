"""Exercise X11 input and clipboard in a dedicated, isolated virtual display."""
from __future__ import annotations

import os
import sys
import threading
import time
import tkinter as tk

import pytest

from voxen.hotkey import GlobalHotkey
from voxen.injector import ClipboardInjector

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("VOXEN_X11_SMOKE") != "1",
    reason="Run explicitly in an isolated Xvfb display",
)


def test_x11_hotkey_press_and_release():
    import pyautogui

    pressed = threading.Event()
    released = threading.Event()
    hotkey = GlobalHotkey("ctrl+space", pressed.set, released.set)
    hotkey.start()
    try:
        hotkey._listener.wait()
        pyautogui.keyDown("ctrl")
        pyautogui.keyDown("space")
        assert pressed.wait(3), "Global shortcut press was not received"
        pyautogui.keyUp("space")
        assert released.wait(3), "Global shortcut release was not received"
    finally:
        pyautogui.keyUp("space")
        pyautogui.keyUp("ctrl")
        hotkey.stop()


def test_x11_clipboard_paste_and_restore():
    import pyperclip

    pyperclip.set_clipboard("xclip")
    pyperclip.copy("original clipboard")
    root = tk.Tk()
    field = tk.Entry(root)
    field.pack()
    root.update()
    field.focus_force()
    root.update()
    errors = []

    def paste():
        try:
            ClipboardInjector().inject("Voxen Linux")
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=paste, daemon=True)
    try:
        thread.start()
        deadline = time.monotonic() + 8
        while thread.is_alive() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        thread.join(timeout=0.1)
        assert not thread.is_alive(), "Clipboard operation timed out"
        assert not errors, errors
        root.update()
        assert field.get() == "Voxen Linux"
        assert pyperclip.paste() == "original clipboard"
    finally:
        root.destroy()
