import pytest

from voxen.domain.hotkey_combo import KeyCombination


def test_parses_trigger_and_modifiers() -> None:
    combo = KeyCombination.parse("ctrl+shift+space")
    assert combo.trigger == "space"
    assert combo.modifiers == {"ctrl", "shift"}


def test_rejects_empty_combination() -> None:
    with pytest.raises(ValueError):
        KeyCombination.parse("")


def test_windows_key_and_command_key_are_the_same_canonical_modifier() -> None:
    assert KeyCombination.parse("win+space") == KeyCombination.parse("cmd+space")


def test_from_keys_normalizes_tk_keysyms() -> None:
    combo = KeyCombination.from_keys({"control_l", "win_l"}, "space")
    assert combo.modifiers == {"ctrl", "cmd"}
    assert combo.trigger == "space"


def test_round_trips_through_config_string() -> None:
    combo = KeyCombination.parse("shift+ctrl+space")
    assert KeyCombination.parse(combo.to_config()) == combo


def test_display_orders_modifiers_consistently() -> None:
    combo = KeyCombination.parse("shift+ctrl+space")
    assert combo.to_display() == "CTRL + SHIFT + SPACE"
