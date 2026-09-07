"""Value object for a keyboard shortcut, independent of any input backend.

Both the global listener (pynput key objects) and the settings-capture UI
(Tk keysyms) need to agree on the same modifier/trigger vocabulary. Before
this module existed, each side kept its own copy of that mapping and they
had drifted apart: pynput has no separate name for the Windows key — it
reports it as ``Key.cmd``, the same value it uses for macOS Command — while
the Tk capture UI mapped ``win_l``/``win_r`` to a distinct ``"win"`` name
with no entry at all for ``cmd``. A hotkey captured with the Windows key
could therefore never match what the listener saw, and Command could not
be captured on macOS at all. Folding both onto one canonical ``"cmd"``
name (matching what pynput itself does) removes the possibility of the two
sides disagreeing; ``to_display`` re-labels it per platform for the user.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd")

_ALIASES = {
    "left ctrl": "ctrl",
    "right ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "control": "ctrl",
    "control_l": "ctrl",
    "control_r": "ctrl",
    "command": "cmd",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
    "super": "cmd",
    "super_l": "cmd",
    "super_r": "cmd",
    "win": "cmd",
    "win_l": "cmd",
    "win_r": "cmd",
    "windows": "cmd",
    "meta": "cmd",
    "meta_l": "cmd",
    "meta_r": "cmd",
    "option": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "page_up": "pageup",
    "page_down": "pagedown",
    "return": "enter",
    "escape": "esc",
    "prior": "pageup",
    "next": "pagedown",
}

_DISPLAY_LABELS = {"cmd": "win" if sys.platform not in ("darwin",) else "cmd"}


def normalize_key_name(name: str) -> str:
    """Map any backend's spelling of a key to the canonical name."""
    return _ALIASES.get(name.strip().lower(), name.strip().lower())


@dataclass(frozen=True)
class KeyCombination:
    """A trigger key plus an unordered set of modifiers, e.g. ``ctrl+space``."""

    trigger: str
    modifiers: frozenset[str]

    @classmethod
    def parse(cls, text: str) -> KeyCombination:
        parts = [normalize_key_name(part) for part in text.split("+") if part.strip()]
        if not parts:
            raise ValueError("La hotkey non può essere vuota.")
        *modifiers, trigger = parts
        return cls(trigger=trigger, modifiers=frozenset(modifiers))

    @classmethod
    def from_keys(cls, modifiers: set[str], trigger: str) -> KeyCombination:
        return cls(trigger=normalize_key_name(trigger), modifiers=frozenset(normalize_key_name(m) for m in modifiers))

    def to_config(self) -> str:
        ordered = [name for name in MODIFIER_ORDER if name in self.modifiers]
        return "+".join([*ordered, self.trigger])

    def to_display(self) -> str:
        parts = (_DISPLAY_LABELS.get(part, part) for part in self.to_config().split("+"))
        return " + ".join(part.strip().upper() for part in parts)
