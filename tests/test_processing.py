from voxen.processing import ProcessingOptions, TextProcessor
from voxen.hotkey import GlobalHotkey
import pytest


def test_processor_normalizes_and_punctuates() -> None:
    result = TextProcessor().process("  ciao   mondo  ", ProcessingOptions())
    assert result == "Ciao mondo."


def test_processor_preserves_existing_punctuation() -> None:
    result = TextProcessor().process("come stai?", ProcessingOptions())
    assert result == "Come stai?"


def test_processor_can_disable_punctuation() -> None:
    result = TextProcessor().process(
        "scrivi codice",
        ProcessingOptions(punctuation=False),
    )
    assert result == "Scrivi codice"


def test_processor_returns_empty_for_whitespace() -> None:
    assert TextProcessor().process(" \t\n", ProcessingOptions()) == ""


def test_processor_preserves_ellipsis() -> None:
    result = TextProcessor().process("aspetta...", ProcessingOptions())
    assert result == "Aspetta..."


def test_processor_preserves_accented_text() -> None:
    result = TextProcessor().process("  perché è già tardi  ", ProcessingOptions())
    assert result == "Perché è già tardi."


@pytest.mark.parametrize("ending", [",", ":", ";", "…", ".", "!", "?"])
def test_processor_preserves_terminal_punctuation(ending: str) -> None:
    result = TextProcessor().process(f"aspetta{ending}", ProcessingOptions())

    assert result == f"Aspetta{ending}"


def test_processor_preserves_quoted_text_without_inventing_punctuation() -> None:
    result = TextProcessor().process('ha detto "ciao"', ProcessingOptions())

    assert result == 'Ha detto "ciao"'


def test_processor_can_return_raw_text() -> None:
    result = TextProcessor().process(
        "  ciao\nmondo  ",
        ProcessingOptions(normalize_whitespace=False, capitalization=False, punctuation=False),
    )
    assert result == "  ciao\nmondo  "


def test_processor_raw_mode_ignores_formatting_options() -> None:
    result = TextProcessor().process(
        "  ciao\nmondo?  ",
        ProcessingOptions(capitalization=True, punctuation=True, normalize_whitespace=False),
    )

    assert result == "  ciao\nmondo?  "


def test_hotkey_parses_configured_combination() -> None:
    hotkey = GlobalHotkey("ctrl+shift+space", lambda: None, lambda: None)
    assert hotkey._trigger == "space"
    assert hotkey._modifiers == {"ctrl", "shift"}


class FakeKey:
    def __init__(self, name: str) -> None:
        self.name = name


def test_hotkey_fires_once_on_press_and_once_on_release() -> None:
    events = []
    hotkey = GlobalHotkey("ctrl+space", lambda: events.append("press"), lambda: events.append("release"))

    hotkey._handle_press(FakeKey("ctrl"))
    hotkey._handle_press(FakeKey("space"))
    hotkey._handle_press(FakeKey("space"))
    hotkey._handle_release(FakeKey("space"))
    hotkey._handle_release(FakeKey("ctrl"))

    assert events == ["press", "release"]


def test_hotkey_does_not_fire_without_modifier() -> None:
    events = []
    hotkey = GlobalHotkey("ctrl+space", lambda: events.append("press"), lambda: events.append("release"))

    hotkey._handle_press(FakeKey("space"))
    hotkey._handle_release(FakeKey("space"))

    assert events == []


def test_hotkey_releases_when_listener_stops_unexpectedly() -> None:
    events = []
    hotkey = GlobalHotkey("ctrl+space", lambda: events.append("press"), lambda: events.append("release"))

    hotkey._handle_press(FakeKey("ctrl"))
    hotkey._handle_press(FakeKey("space"))
    hotkey._handle_listener_stop()

    assert events == ["press", "release"]
    assert hotkey._pressed is False
    assert hotkey._keys_down == set()
