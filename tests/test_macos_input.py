"""Deterministic Quartz adapter tests; no host permissions or global input."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from voxen.domain.hotkey_combo import KeyCombination
from voxen.infrastructure.macos_input import InputPermissionError, MacHotkey, MacPasteAutomation


def quartz():
    q = SimpleNamespace(
        kCGEventKeyDown=10, kCGEventKeyUp=11, kCGEventFlagsChanged=12,
        kCGEventTapDisabledByTimeout=20, kCGEventTapDisabledByUserInput=21,
        kCGEventFlagMaskControl=1, kCGEventFlagMaskAlternate=2, kCGEventFlagMaskShift=4,
        kCGEventFlagMaskCommand=8, kCGKeyboardEventKeycode=9, kCGHIDEventTap=0,
        kCGSessionEventTap=1, kCGHeadInsertEventTap=0, kCGEventTapOptionListenOnly=1,
        CGPreflightListenEventAccess=Mock(return_value=True),
        CGPreflightPostEventAccess=Mock(return_value=True),
        CGEventTapCreate=Mock(return_value="tap"), CGEventTapEnable=Mock(),
        CGEventGetIntegerValueField=lambda event, _: event[0],
        CGEventGetFlags=lambda event: event[1],
        CGEventKeyboardGetUnicodeString=lambda event, *_: (len(event[2]), event[2]),
        CGEventCreateKeyboardEvent=Mock(side_effect=lambda _, code, down: (code, down)),
        CGEventSetFlags=Mock(), CGEventPost=Mock(),
    )
    return q


def make_listener(combo="cmd+shift+space"):
    q = quartz()
    cf = SimpleNamespace(CFMachPortCreateRunLoopSource=Mock(return_value="source"),
                         CFRunLoopGetMain=Mock(return_value="main"),
                         CFRunLoopAddSource=Mock(), CFRunLoopRemoveSource=Mock(),
                         CFMachPortInvalidate=Mock(), kCFRunLoopCommonModes="common")
    calls = []
    listener = MacHotkey(KeyCombination.parse(combo), lambda: calls.append("down"),
                         lambda: calls.append("up"), quartz=q, cf=cf)
    return listener, q, cf, calls


def event(listener, kind, code=49, flags=12, chars=""):
    payload = (code, flags, chars)
    assert listener.callback(None, kind, payload, None) is payload


def test_tap_lifecycle_and_permission_denial():
    listener, q, cf, _ = make_listener()
    q.CGPreflightListenEventAccess.return_value = False
    with pytest.raises(InputPermissionError, match="Input Monitoring"):
        listener.start()
    q.CGEventTapCreate.assert_not_called()
    q.CGPreflightListenEventAccess.return_value = True
    listener.start()
    listener.start()
    q.CGEventTapCreate.assert_called_once()
    cf.CFRunLoopAddSource.assert_called_once_with("main", "source", "common")
    listener.stop()
    listener.stop()
    cf.CFRunLoopRemoveSource.assert_called_once_with("main", "source", "common")
    cf.CFMachPortInvalidate.assert_called_once_with("tap")


def test_repeat_modifier_release_and_repress():
    listener, q, _, calls = make_listener()
    event(listener, q.kCGEventKeyDown)
    event(listener, q.kCGEventKeyDown)
    event(listener, q.kCGEventFlagsChanged, flags=8)
    event(listener, q.kCGEventFlagsChanged)
    event(listener, q.kCGEventKeyUp)
    assert calls == ["down", "up", "down", "up"]


def test_layout_unicode_and_release_by_physical_key():
    listener, q, _, calls = make_listener("cmd+z")
    event(listener, q.kCGEventKeyDown, code=6, flags=8, chars="z")
    event(listener, q.kCGEventKeyUp, code=6, flags=8, chars="x")
    assert calls == ["down", "up"]


def test_disabled_tap_releases_once_and_recovers():
    listener, q, _, calls = make_listener()
    listener.start()
    event(listener, q.kCGEventKeyDown)
    event(listener, q.kCGEventTapDisabledByTimeout)
    event(listener, q.kCGEventTapDisabledByUserInput)
    event(listener, q.kCGEventKeyDown)
    event(listener, q.kCGEventKeyUp)
    assert calls == ["down", "up", "down", "up"]
    assert q.CGEventTapEnable.call_count == 3


def test_failed_source_creation_invalidates_tap():
    listener, _, cf, _ = make_listener()
    cf.CFMachPortCreateRunLoopSource.return_value = None
    with pytest.raises(RuntimeError, match="run-loop"):
        listener.start()
    cf.CFMachPortInvalidate.assert_called_once_with("tap")
    assert listener.tap is None


def test_native_paste_checks_access_and_posts_pair():
    q = quartz()
    paste = MacPasteAutomation(q)
    q.CGPreflightPostEventAccess.return_value = False
    with pytest.raises(InputPermissionError, match="Accessibility"):
        paste.hotkey("command", "v")
    q.CGEventPost.assert_not_called()
    q.CGPreflightPostEventAccess.return_value = True
    paste.hotkey("command", "v")
    assert [call.args for call in q.CGEventPost.call_args_list] == [(0, (9, True)), (0, (9, False))]


def test_paste_is_safe_from_existing_delivery_worker():
    q = quartz()
    with ThreadPoolExecutor(max_workers=1) as worker:
        worker.submit(MacPasteAutomation(q).hotkey, "command", "v").result(timeout=2)
    assert q.CGEventPost.call_count == 2


def test_tap_cannot_be_started_on_worker_thread():
    listener, q, _, _ = make_listener()
    with ThreadPoolExecutor(max_workers=1) as worker:
        with pytest.raises(RuntimeError, match="main thread"):
            worker.submit(listener.start).result(timeout=2)
    q.CGEventTapCreate.assert_not_called()


def test_control_character_matches_logical_letter_not_ansi_position():
    listener, q, _, calls = make_listener("ctrl+z")
    event(listener, q.kCGEventKeyDown, code=0, flags=1, chars="\x1a")
    event(listener, q.kCGEventKeyUp, code=0, flags=1)
    assert calls == ["down", "up"]
