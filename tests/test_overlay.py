"""Regression tests for the first-show pill flicker.

The pill used to appear slightly larger on the very first dictation and
"bounce" when the hotkey was released. Root cause: the native rounded
region was only applied *before* the first map, where
``winfo_width/height`` can disagree with the mapped size, and nothing
re-applied it afterwards; re-setting identical geometry could also make
the window manager re-settle the window for a frame.
"""

from __future__ import annotations

import ctypes

from voxen.presentation import overlay as ov


class FakeWindow:
    def __init__(self, width: int = 320, height: int = 64) -> None:
        self._width = width
        self._height = height
        self.geometry_calls: list[str] = []
        self.deiconify_calls = 0
        self.withdraw_calls = 0
        self.update_idletasks_calls = 0
        self.update_calls = 0
        self.viewable = False
        self.bindings: dict[str, object] = {}

    def geometry(self, spec: str) -> None:
        self.geometry_calls.append(spec)

    def update_idletasks(self) -> None:
        self.update_idletasks_calls += 1

    def update(self) -> None:
        self.update_calls += 1

    def deiconify(self) -> None:
        self.deiconify_calls += 1
        self.viewable = True

    def withdraw(self) -> None:
        self.withdraw_calls += 1
        self.viewable = False

    def winfo_width(self) -> int:
        return self._width

    def winfo_height(self) -> int:
        return self._height

    def winfo_id(self) -> int:
        return 999

    def winfo_viewable(self) -> int:
        return 1 if self.viewable else 0

    def bind(self, sequence: str, func, add=None):
        self.bindings[sequence] = func
        return "binding"


class FakeRoot:
    def __init__(self) -> None:
        self.after_idle_calls: list = []
        self.after_cancel_calls: list = []

    def after_idle(self, func):
        self.after_idle_calls.append(func)
        return "idle-1"

    def after_cancel(self, ident) -> None:
        self.after_cancel_calls.append(ident)

    def winfo_id(self) -> int:
        return 111

    def winfo_vrootx(self) -> int:
        return 0

    def winfo_vrooty(self) -> int:
        return 0

    def winfo_screenwidth(self) -> int:
        return 1920

    def winfo_screenheight(self) -> int:
        return 1080


class FakeGdi32:
    def __init__(self) -> None:
        self.created: list = []
        self.deleted: list = []

    def CreateRoundRectRgn(self, left, top, right, bottom, width, height):
        self.created.append((left, top, right, bottom, width, height))
        return 1234

    def DeleteObject(self, handle) -> bool:
        self.deleted.append(handle)
        return True


class FakeUser32:
    def __init__(self) -> None:
        self.set_calls: list = []

    def SetWindowRgn(self, hwnd, region, redraw) -> int:
        self.set_calls.append((hwnd, region, redraw))
        return 1


class FakeWindll:
    def __init__(self) -> None:
        self.gdi32 = FakeGdi32()
        self.user32 = FakeUser32()


def make_overlay(monkeypatch, width: int = 320, height: int = 64):
    windll = FakeWindll()
    monkeypatch.setattr(ctypes, "windll", windll, raising=False)
    app = object.__new__(ov.RecordingOverlay)
    app._root = FakeRoot()
    app._window = FakeWindow(width, height)
    app._mode = "listening"
    app._visible = False
    app._geometry = None
    app._applied_size = None
    app._native_region = True
    # Skip the animation loop: these tests cover mapping/region only.
    app._animation_id = "running"
    app._level_provider = lambda: 0.0
    return app, windll


def test_show_applies_region_after_map(monkeypatch) -> None:
    app, windll = make_overlay(monkeypatch)

    app.show("listening")

    assert app._window.geometry_calls == ["320x64+800+1000"]
    assert app._window.deiconify_calls == 1
    # Once pre-map (via _position_window) and once post-map (forced refresh).
    assert windll.user32.set_calls == [(999, 1234, True)] * 2
    assert app._applied_size == (320, 64)
    assert len(app._root.after_idle_calls) == 1


def test_second_show_reuses_geometry_but_refreshes_region(monkeypatch) -> None:
    app, windll = make_overlay(monkeypatch)

    app.show("listening")
    app.hide()
    app._animation_id = "running"
    app.show("processing")

    # Same target: no geometry reset (no manager re-settle bounce),
    # but the region is force-refreshed for the fresh map.
    assert app._window.geometry_calls == ["320x64+800+1000"]
    assert len(windll.user32.set_calls) == 3


def test_redundant_region_application_is_skipped(monkeypatch) -> None:
    app, windll = make_overlay(monkeypatch)

    app._apply_native_region()
    app._apply_native_region()

    assert len(windll.user32.set_calls) == 1

    app._window._width = 321
    app._apply_native_region()

    assert len(windll.user32.set_calls) == 2


def test_configure_reapplies_only_on_size_change(monkeypatch) -> None:
    app, windll = make_overlay(monkeypatch)
    app._visible = True

    app._on_configure(None)
    app._on_configure(None)

    assert len(windll.user32.set_calls) == 1

    app._window._height = 65
    app._on_configure(None)

    assert len(windll.user32.set_calls) == 2


def test_reapply_after_map_is_a_noop_once_hidden(monkeypatch) -> None:
    app, windll = make_overlay(monkeypatch)

    app.show("listening")
    calls_after_show = len(windll.user32.set_calls)
    app.hide()
    app._reapply_after_map()

    assert len(windll.user32.set_calls) == calls_after_show
