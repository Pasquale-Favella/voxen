from __future__ import annotations

import time
import sys


class ClipboardInjector:
    def inject(self, text: str) -> None:
        try:
            import pyautogui
            import pyperclip
        except ImportError as exc:
            raise RuntimeError("Installa pyautogui e pyperclip per incollare il testo.") from exc

        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None
        pyperclip.copy(text)
        time.sleep(0.05)
        paste_modifier = "command" if sys.platform == "darwin" else "ctrl"
        pyautogui.hotkey(paste_modifier, "v")
        time.sleep(0.15)
        if previous is not None:
            pyperclip.copy(previous)
