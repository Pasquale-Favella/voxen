"""macOS input through Quartz, without Carbon keyboard-layout calls."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from ..domain.hotkey_combo import KeyCombination, normalize_key_name

logger = logging.getLogger(__name__)

# Virtual keycodes for non-printing keys and ANSI fallback for control characters.
_SPECIAL = {
    36: "enter", 48: "tab", 49: "space", 51: "backspace", 53: "esc", 76: "enter",
    115: "home", 116: "pageup", 117: "delete", 119: "end", 121: "pagedown",
    123: "left", 124: "right", 125: "down", 126: "up",
    122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5", 97: "f6",
    98: "f7", 100: "f8", 101: "f9", 109: "f10", 103: "f11", 111: "f12",
    105: "f13", 107: "f14", 113: "f15", 106: "f16", 64: "f17", 79: "f18", 80: "f19", 90: "f20",
}
_ANSI = dict(zip(
    (0, 11, 8, 2, 14, 3, 5, 4, 34, 38, 40, 37, 46, 45, 31, 35, 12, 15, 1, 17, 32, 9, 13, 7, 16, 6,
     29, 18, 19, 20, 21, 23, 22, 26, 28, 25),
    "abcdefghijklmnopqrstuvwxyz0123456789", strict=True,
))


class InputPermissionError(RuntimeError):
    """macOS did not grant the requested input capability."""


def require_main_thread() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("macOS input services must be managed on the main thread.")


def key_name(quartz, event, code: int) -> str:
    if code in _SPECIAL:
        return _SPECIAL[code]
    count, chars = quartz.CGEventKeyboardGetUnicodeString(event, 16, None, None)
    chars = chars[:count] if chars is not None else ""
    if isinstance(chars, str):
        value = chars
    else:
        value = "".join(chr(unit) for unit in chars)
    if len(value) == 1 and value.isprintable():
        return normalize_key_name(value)
    return _ANSI.get(code, "")


class MacHotkey:
    """Listen-only event tap owned by the existing Tk/Cocoa main run loop."""

    def __init__(self, combination: KeyCombination, on_press: Callable, on_release: Callable, *, quartz=None, cf=None):
        if quartz is None:
            import Quartz as quartz
        if cf is None:
            import CoreFoundation as cf
        self.q = quartz
        self.cf = cf
        self.combo = combination
        self.on_press = on_press
        self.on_release = on_release
        self.tap = None
        self.source = None
        self.loop = None
        self.active = False
        self.down: dict[int, str] = {}
        # Keep a strong reference to the C callback for the tap lifetime.
        self.callback = self._event

    def start(self) -> None:
        require_main_thread()
        if self.tap is not None:
            return
        q, cf = self.q, self.cf
        if not q.CGPreflightListenEventAccess():
            raise InputPermissionError("Allow Voxen in System Settings → Privacy & Security → Input Monitoring, then retry the shortcut.")
        mask = sum(1 << event for event in (q.kCGEventKeyDown, q.kCGEventKeyUp, q.kCGEventFlagsChanged))
        self.tap = q.CGEventTapCreate(q.kCGSessionEventTap, q.kCGHeadInsertEventTap,
                                     q.kCGEventTapOptionListenOnly, mask, self.callback, None)
        if self.tap is None:
            raise RuntimeError("Could not create the macOS keyboard event tap.")
        try:
            self.source = cf.CFMachPortCreateRunLoopSource(None, self.tap, 0)
            if self.source is None:
                raise RuntimeError("Could not create the keyboard run-loop source.")
            self.loop = cf.CFRunLoopGetMain()
            cf.CFRunLoopAddSource(self.loop, self.source, cf.kCFRunLoopCommonModes)
            q.CGEventTapEnable(self.tap, True)
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        require_main_thread()
        self.active = False
        self.down.clear()
        if self.tap is None:
            return
        if self.source is not None and self.loop is not None:
            self.cf.CFRunLoopRemoveSource(self.loop, self.source, self.cf.kCFRunLoopCommonModes)
        self.cf.CFMachPortInvalidate(self.tap)
        self.tap = self.source = self.loop = None

    def _reset(self) -> None:
        self.down.clear()
        if self.active:
            self.active = False
            self.on_release()

    def _event(self, _proxy, kind, event, _refcon):
        q = self.q
        try:
            if kind in (q.kCGEventTapDisabledByTimeout, q.kCGEventTapDisabledByUserInput):
                self._reset()
                if self.tap is not None:
                    q.CGEventTapEnable(self.tap, True)
                return event
            if kind not in (q.kCGEventKeyDown, q.kCGEventKeyUp, q.kCGEventFlagsChanged):
                return event
            code = q.CGEventGetIntegerValueField(event, q.kCGKeyboardEventKeycode)
            if kind == q.kCGEventKeyDown:
                if code not in self.down:
                    self.down[code] = key_name(q, event, code)
            elif kind == q.kCGEventKeyUp:
                self.down.pop(code, None)
            flags = q.CGEventGetFlags(event)
            modifiers = {name for name, flag in (
                ("ctrl", q.kCGEventFlagMaskControl), ("alt", q.kCGEventFlagMaskAlternate),
                ("shift", q.kCGEventFlagMaskShift), ("cmd", q.kCGEventFlagMaskCommand),
            ) if flags & flag}
            active = self.combo.trigger in self.down.values() and self.combo.modifiers.issubset(modifiers)
            if active != self.active:
                self.active = active
                (self.on_press if active else self.on_release)()
        except Exception:
            logger.exception("macOS keyboard event failed")
            self._reset()
        return event


class MacPasteAutomation:
    """Post Command+V directly; no keyboard-layout lookup or pyautogui on macOS."""

    def __init__(self, quartz=None):
        if quartz is None:
            import Quartz as quartz
        self.q = quartz

    def hotkey(self, modifier: str, key: str) -> None:
        if (modifier, key) != ("command", "v"):
            raise ValueError("Only Command+V is supported.")
        # Delivery runs on the STT worker. These Quartz event APIs do not
        # use the main-thread-only Carbon input-source lookup.
        q = self.q
        if not q.CGPreflightPostEventAccess():
            raise InputPermissionError("Allow Voxen in System Settings → Privacy & Security → Accessibility.")
        events = [q.CGEventCreateKeyboardEvent(None, 9, down) for down in (True, False)]
        if any(event is None for event in events):
            raise RuntimeError("Could not create macOS paste events.")
        for event in events:
            q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand)
            q.CGEventPost(q.kCGHIDEventTap, event)
