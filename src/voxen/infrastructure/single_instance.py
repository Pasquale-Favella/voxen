"""One desktop instance per user profile; local, payload-free activation."""

from __future__ import annotations

import errno
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

POLL_SECONDS = 0.05
ACTIVATION_TIMEOUT = 10.0
UI_POLL_MS = 150


class InstanceGate:
    """An OS-owned advisory lock, plus a coalescing reopen request.

    Never unlink the lock file: doing so could allow two owners to lock
    different inodes. The OS releases the lock on process exit or crash.
    Only the owner consumes requests; contenders wait for acknowledgment or
    take ownership if the primary exits before handling the request.
    """

    def __init__(self, directory: Path):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._request = directory / "reopen"
        self._handle = (directory / "owner.lock").open("a+b")
        self._owned = False

    def __enter__(self) -> InstanceGate:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _try_acquire(self) -> bool:
        if self._owned:
            return True
        self._handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                return False
            raise
        self._owned = True
        return True

    def start_or_activate(self, timeout: float = ACTIVATION_TIMEOUT) -> bool:
        """True for the primary; False when an existing owner accepted reopen."""
        if self._try_acquire():
            return True
        # No PID lookup, network socket or message contents. Concurrent launch
        # requests intentionally coalesce into one dashboard activation.
        try:
            fd = os.open(self._request, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass  # Another contender already requested the same activation.
        else:
            os.close(fd)
        deadline = time.monotonic() + timeout
        while True:
            if not self._request.exists():
                return False
            if self._try_acquire():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Voxen is already running but did not respond to the reopen request.")
            time.sleep(min(POLL_SECONDS, remaining))

    def consume_activation(self) -> bool:
        if not self._owned:
            raise RuntimeError("Only the primary Voxen instance can consume activation requests.")
        try:
            self._request.unlink()
        except FileNotFoundError:
            return False
        except PermissionError:
            # Windows may briefly deny deletion while a contender creates the
            # marker. Leave it pending for the next poll instead of losing it.
            if sys.platform != "win32":
                raise
            return False
        return True

    def close(self) -> None:
        if not self._handle.closed:
            # Closing the owning file descriptor releases the OS lock.
            self._handle.close()
        self._owned = False


def install_activation_handler(root, gate: InstanceGate, show: Callable[[], None]) -> Callable[[], None]:
    """Dispatch requests on Tk's main thread, never from a background worker."""
    def poll() -> None:
        nonlocal timer
        try:
            if gate.consume_activation():
                show()
        finally:
            timer = root.after(UI_POLL_MS, poll)

    timer = root.after(0, poll)

    def cancel() -> None:
        root.after_cancel(timer)

    return cancel
