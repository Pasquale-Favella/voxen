import sys

import pytest

from voxen.injector import ClipboardInjector


class FakeClipboard:
    def __init__(self, value: str) -> None:
        self.value = value

    def paste(self) -> str:
        return self.value

    def copy(self, value: str) -> None:
        self.value = value


class FakeAutomation:
    def __init__(self, fail: bool = False) -> None:
        self.calls = []
        self.fail = fail

    def hotkey(self, modifier: str, key: str) -> None:
        if self.fail:
            raise RuntimeError("paste failed")
        self.calls.append((modifier, key))


class FakeRichClipboard:
    def __init__(self) -> None:
        self.value = ("html", b"<b>previous</b>")
        self.restored = None

    def snapshot(self):
        return self.value

    def set_text(self, text: str) -> None:
        self.value = ("text", text.encode())

    def restore(self, snapshot) -> None:
        self.restored = snapshot
        self.value = snapshot


def test_injector_restores_previous_clipboard() -> None:
    clipboard = FakeClipboard("previous")
    automation = FakeAutomation()
    injector = ClipboardInjector(sleep=lambda _delay: None, clipboard=clipboard, automation=automation)

    injector.inject("transcript")

    assert clipboard.value == "previous"
    expected_modifier = "command" if sys.platform == "darwin" else "ctrl"
    assert automation.calls == [(expected_modifier, "v")]


def test_injector_restores_clipboard_when_paste_fails() -> None:
    clipboard = FakeClipboard("previous")
    injector = ClipboardInjector(
        sleep=lambda _delay: None,
        clipboard=clipboard,
        automation=FakeAutomation(fail=True),
    )

    with pytest.raises(RuntimeError, match="Impossibile incollare il testo"):
        injector.inject("transcript")

    assert clipboard.value == "previous"


def test_injector_restores_an_opaque_clipboard_snapshot() -> None:
    clipboard = FakeRichClipboard()
    injector = ClipboardInjector(
        sleep=lambda _delay: None,
        backend=clipboard,
        automation=FakeAutomation(),
    )

    injector.inject("transcript")

    assert clipboard.restored == ("html", b"<b>previous</b>")