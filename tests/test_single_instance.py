"""Cross-process single-instance tests with explicit synchronization."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from voxen.infrastructure.single_instance import InstanceGate, install_activation_handler

CHILD = """
import sys
from pathlib import Path
from voxen.infrastructure.single_instance import InstanceGate
directory = Path(sys.argv[1])
with InstanceGate(directory) as gate:
    primary = gate.start_or_activate(timeout=8)
    print("primary" if primary else "activated", flush=True)
    if primary and sys.argv[2] == "hold":
        (directory / "ready").touch()
        sys.stdin.read()
"""


def spawn(directory, mode="activate"):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.Popen([sys.executable, "-c", CHILD, str(directory), mode],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env)


def wait_for(path):
    deadline = time.monotonic() + 5
    while not path.exists():
        if time.monotonic() >= deadline:
            pytest.fail(f"Timed out waiting for {path.name}")
        time.sleep(0.01)


def result(process):
    output, errors = process.communicate(timeout=12)
    assert process.returncode == 0, errors
    return output.strip()


def cleanup(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=5)


def test_concurrent_launches_reuse_primary(tmp_path):
    with InstanceGate(tmp_path) as primary:
        assert primary.start_or_activate()
        children = [spawn(tmp_path) for _ in range(4)]
        try:
            # Each request is acknowledged by the owner; no child can acquire
            # the real OS lock while it is held.
            deadline = time.monotonic() + 10
            activations = 0
            while any(child.poll() is None for child in children):
                activations += primary.consume_activation()
                if time.monotonic() >= deadline:
                    pytest.fail("Contenders did not receive activation acknowledgment")
                time.sleep(0.01)
            assert activations >= 1
            assert [result(child) for child in children] == ["activated"] * 4
        finally:
            for child in children:
                cleanup(child)


def test_crashed_owner_releases_os_lock(tmp_path):
    primary = spawn(tmp_path, "hold")
    try:
        wait_for(tmp_path / "ready")
        primary.kill()
        primary.communicate(timeout=5)
        with InstanceGate(tmp_path) as successor:
            assert successor.start_or_activate()
    finally:
        cleanup(primary)


def test_contender_takes_over_if_owner_exits_before_ack(tmp_path):
    primary = spawn(tmp_path, "hold")
    secondary = None
    try:
        wait_for(tmp_path / "ready")
        secondary = spawn(tmp_path)
        wait_for(tmp_path / "reopen")
        primary.communicate(timeout=5)
        assert result(secondary) == "primary"
    finally:
        cleanup(primary)
        if secondary is not None:
            cleanup(secondary)


def test_unresponsive_owner_never_allows_duplicate(tmp_path):
    with InstanceGate(tmp_path) as primary:
        assert primary.start_or_activate()
        with InstanceGate(tmp_path) as secondary:
            with pytest.raises(TimeoutError, match="already running"):
                secondary.start_or_activate(timeout=0)
            with pytest.raises(RuntimeError, match="Only the primary"):
                secondary.consume_activation()
        assert primary.consume_activation()
        assert not primary.consume_activation()


def test_main_loop_consumes_and_coalesces_requests(tmp_path):
    class Root:
        def __init__(self):
            self.callbacks = {}

        def after(self, delay, callback):
            self.callbacks[delay] = callback
            return delay

        def after_cancel(self, timer):
            del self.callbacks[timer]

    root = Root()
    calls = []
    with InstanceGate(tmp_path) as gate:
        assert gate.start_or_activate()
        cancel = install_activation_handler(root, gate, lambda: calls.append("show"))
        (tmp_path / "reopen").touch()
        (tmp_path / "reopen").touch()
        root.callbacks.pop(0)()
        assert calls == ["show"]
        root.callbacks.pop(150)()
        assert calls == ["show"]
        cancel()
        assert root.callbacks == {}
