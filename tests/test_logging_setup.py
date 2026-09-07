import logging
import sys

from voxen.infrastructure import logging_setup


def test_configure_creates_a_rotating_file_handler(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(logging_setup, "_log_dir", lambda: tmp_path / "logs")
    root_logger = logging.getLogger("voxen")
    original_handlers = list(root_logger.handlers)

    try:
        log_path = logging_setup.configure()
        logging.getLogger("voxen.something").warning("hello")
        for handler in root_logger.handlers:
            handler.flush()

        assert log_path == tmp_path / "logs" / "voxen.log"
        assert log_path.exists()
        assert "hello" in log_path.read_text(encoding="utf-8")
    finally:
        for handler in list(root_logger.handlers):
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()


def test_log_dir_uses_platform_appropriate_location(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(logging_setup.Path, "home", lambda: tmp_path)

    assert logging_setup._log_dir() == tmp_path / "Library" / "Logs" / "Voxen"
