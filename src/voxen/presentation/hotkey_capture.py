"""UI state machine for capturing a new hotkey combination.

Previously ``VoxenApp._capture_hotkey`` kept its own private
``modifier_names`` dict, separate from (and missing several entries
present in) ``GlobalHotkey``'s own copy — the source of the win-key/cmd-key
bug described in ``domain/hotkey_combo.py``. This controller now goes
through the same ``KeyCombination`` value object the listener uses, so the
combination the user captures here is guaranteed to be one the listener can
actually recognize.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from ..domain.hotkey_combo import MODIFIER_ORDER, KeyCombination, normalize_key_name
from . import theme
from .shapes import RoundedButton

_MODIFIER_NAMES = set(MODIFIER_ORDER)


class HotkeyCapture:
    def __init__(
        self,
        button: RoundedButton,
        hotkey_var: tk.StringVar,
        button_var: tk.StringVar,
        hint_var: tk.StringVar,
        on_change: Callable[[str], None],
    ) -> None:
        self._button = button
        self._hotkey_var = hotkey_var
        self._button_var = button_var
        self._hint_var = hint_var
        self._on_change = on_change
        self._keys_down: set[str] = set()
        self._binding: str | None = None
        self.capturing = False

    @staticmethod
    def display_text(hotkey: str) -> str:
        return KeyCombination.parse(hotkey).to_display()

    def begin(self) -> None:
        self._keys_down = set()
        self.capturing = True
        self._button_var.set("PRESS YOUR COMBINATION")
        self._hint_var.set("For example: hold Ctrl and press Space")
        self._button.set_colors(bg=theme.CAPTURE_BG, fg=theme.CAPTURE_FG, active_bg=theme.CAPTURE_ACTIVE_BG)
        self._button.focus_set()
        self._binding = self._button.bind("<KeyPress>", self._on_key_press, add="+")

    def cancel(self, revert_to: str) -> None:
        self._end_binding()
        self._keys_down = set()
        self._hotkey_var.set(revert_to)
        self._button_var.set(self.display_text(revert_to))
        self._hint_var.set("Click the button, then press your key combination")
        self._on_change(revert_to)

    def _on_key_press(self, event: tk.Event) -> str:
        key = normalize_key_name(event.keysym.lower())
        if key in _MODIFIER_NAMES:
            self._keys_down.add(key)
            return "break"
        combo = KeyCombination.from_keys(self._keys_down, key)
        self._hotkey_var.set(combo.to_config())
        self._button_var.set(combo.to_display())
        self._hint_var.set("Hotkey updated. Save settings to keep it.")
        self.finish()
        return "break"

    def finish(self) -> None:
        """End capture mode, keeping whatever value is currently set."""
        self._end_binding()
        self._on_change(self._hotkey_var.get())

    def _end_binding(self) -> None:
        self.capturing = False
        if self._binding is not None:
            self._button.unbind("<KeyPress>", self._binding)
            self._binding = None
        self._button.set_colors(bg=theme.BUTTON_BG, fg=theme.BUTTON_FG, active_bg=theme.BUTTON_ACTIVE_BG)
