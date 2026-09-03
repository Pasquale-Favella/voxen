from voxen.processing import ProcessingOptions, TextProcessor
from voxen.hotkey import GlobalHotkey


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


def test_hotkey_parses_configured_combination() -> None:
    hotkey = GlobalHotkey("ctrl+shift+space", lambda: None, lambda: None)
    assert hotkey._trigger == "space"
    assert hotkey._modifiers == {"ctrl", "shift"}
