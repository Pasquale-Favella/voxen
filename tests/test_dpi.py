"""Tests for process DPI awareness declaration."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

import voxen.infrastructure.dpi as dpi_module


def _patch_windll(monkeypatch, *, platform="win32", user32=None, shcore=None) -> None:
    monkeypatch.setattr(dpi_module.sys, "platform", platform)
    namespaces = {}
    if user32 is not None:
        namespaces["user32"] = user32
    if shcore is not None:
        namespaces["shcore"] = shcore
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(**namespaces), raising=False)


def test_noop_off_windows(monkeypatch) -> None:
    _patch_windll(monkeypatch, platform="linux")

    assert dpi_module.ensure_awareness() is None


def test_prefers_per_monitor_v2(monkeypatch) -> None:
    calls = []

    def set_context(value) -> int:
        calls.append(value)
        return 1

    _patch_windll(
        monkeypatch,
        user32=SimpleNamespace(SetProcessDpiAwarenessContext=set_context),
        shcore=SimpleNamespace(SetProcessDpiAwareness=lambda _v: (_ for _ in ()).throw(AssertionError("unused"))),
    )

    assert dpi_module.ensure_awareness() == "per-monitor-v2"
    assert calls == [-4]


def test_falls_back_to_shcore_when_v2_missing(monkeypatch) -> None:
    _patch_windll(
        monkeypatch,
        user32=SimpleNamespace(),  # no SetProcessDpiAwarenessContext export
        shcore=SimpleNamespace(SetProcessDpiAwareness=lambda value: 0 if value == 2 else 1),
    )

    assert dpi_module.ensure_awareness() == "per-monitor"


def test_falls_back_to_system_aware(monkeypatch) -> None:
    _patch_windll(
        monkeypatch,
        user32=SimpleNamespace(
            SetProcessDpiAwarenessContext=lambda _v: 0,
            SetProcessDPIAware=lambda: 1,
        ),
        shcore=SimpleNamespace(SetProcessDpiAwareness=lambda _v: 1),  # E_FAIL
    )

    assert dpi_module.ensure_awareness() == "system"


def test_returns_none_when_everything_fails(monkeypatch) -> None:
    def boom(*_args) -> int:
        raise OSError("not implemented")

    _patch_windll(
        monkeypatch,
        user32=SimpleNamespace(SetProcessDpiAwarenessContext=boom, SetProcessDPIAware=boom),
        shcore=SimpleNamespace(SetProcessDpiAwareness=boom),
    )

    assert dpi_module.ensure_awareness() is None


def test_returns_none_without_windll(monkeypatch) -> None:
    monkeypatch.setattr(dpi_module.sys, "platform", "win32")
    monkeypatch.delattr(ctypes, "windll", raising=False)

    assert dpi_module.ensure_awareness() is None
