from __future__ import annotations

from collections.abc import Callable


class GlobalHotkey:
    def __init__(self, hotkey: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        self.hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self._listener = None
        self._keyboard = None
        self._pressed = False
        self._keys_down: set[str] = set()
        self._stopping = False
        parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
        if not parts:
            raise ValueError("La hotkey non può essere vuota.")
        self._trigger = self._normalize(parts[-1])
        self._modifiers = {self._normalize(part) for part in parts[:-1]}

    @staticmethod
    def _normalize(key: str) -> str:
        return {
            "left ctrl": "ctrl",
            "right ctrl": "ctrl",
            "ctrl_l": "ctrl",
            "ctrl_r": "ctrl",
            "control": "ctrl",
            "command": "cmd",
            "cmd_l": "cmd",
            "cmd_r": "cmd",
            "option": "alt",
            "alt_l": "alt",
            "alt_r": "alt",
            "alt_gr": "alt",
            "shift_l": "shift",
            "shift_r": "shift",
            "win_l": "win",
            "win_r": "win",
            "page_up": "pageup",
            "page_down": "pagedown",
            "return": "enter",
            "escape": "esc",
        }.get(key, key)

    def _key_name(self, key) -> str:
        char = getattr(key, "char", None)
        if char:
            return self._normalize(char.lower())
        name = getattr(key, "name", None)
        if name:
            return self._normalize(name.lower())
        return self._normalize(str(key).strip("'").lower())

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError("Installa pynput per usare la hotkey globale.") from exc

        self._keyboard = keyboard
        self._stopping = False
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
            on_stop=self._handle_listener_stop,
        )
        try:
            self._listener.start()
        except Exception as exc:
            self._listener = None
            raise RuntimeError(f"Impossibile attivare la hotkey globale: {exc}") from exc

    def _handle_listener_stop(self) -> None:
        was_pressed = self._pressed
        self._keys_down.clear()
        self._pressed = False
        if was_pressed and not self._stopping:
            self.on_release()

    def _handle_press(self, key) -> None:
        name = self._key_name(key)
        self._keys_down.add(name)
        active = self._trigger in self._keys_down and self._modifiers.issubset(self._keys_down)
        if active and not self._pressed:
            self._pressed = True
            self.on_press()

    def _handle_release(self, key) -> None:
        name = self._key_name(key)
        self._keys_down.discard(name)
        active = self._trigger in self._keys_down and self._modifiers.issubset(self._keys_down)
        if not active and self._pressed:
            self._pressed = False
            self.on_release()

    def stop(self) -> None:
        self._stopping = True
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._keys_down.clear()
        self._pressed = False
