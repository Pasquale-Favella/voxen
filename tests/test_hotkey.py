
from voxen.hotkey import GlobalHotkey


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


def test_hotkey_recognizes_windows_key_captured_as_cmd() -> None:
    """pynput reports the Windows key as ``cmd`` — a "win+..." hotkey must still match it."""
    events = []
    hotkey = GlobalHotkey("win+space", lambda: events.append("press"), lambda: events.append("release"))

    assert hotkey._modifiers == {"cmd"}

    hotkey._handle_press(FakeKey("cmd"))
    hotkey._handle_press(FakeKey("space"))

    assert events == ["press"]
