import subprocess

import pytest

from voxen.config import ConfigStore
from voxen.infrastructure import linux, logging_setup
from voxen.stt import models_root


def test_xdg_paths(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert ConfigStore().path == tmp_path / "config/voxen/config.json"
    assert models_root() == tmp_path / "data/voxen/models"
    assert logging_setup._log_dir() == tmp_path / "state/voxen/logs"


def test_require_x11(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    linux.require_x11()
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    with pytest.raises(SystemExit, match="X11"):
        linux.require_x11()


def test_portal_dark_and_unavailable(monkeypatch):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "test")
    monkeypatch.setattr(linux.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, "(<uint32 1>,)", ""))
    assert linux.read_portal_appearance() == "dark"
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS")
    assert linux.read_portal_appearance() is None
