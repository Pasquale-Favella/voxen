from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_VERSION = 1
SUPPORTED_MODELS = ("tiny", "base", "small")
SUPPORTED_LANGUAGES = ("auto", "it", "en", "ja", "fr", "de", "es")

# One predicate per field with a business rule beyond "matches the default's
# type". Adding a new constrained field means adding one entry here, not
# editing a chain of if/elif branches.
_FIELD_VALIDATORS: dict[str, Callable[[object], bool]] = {
    "model": lambda value: value in SUPPORTED_MODELS,
    "language": lambda value: value in SUPPORTED_LANGUAGES,
    "sample_rate": lambda value: value > 0,
}


@dataclass
class AppConfig:
    hotkey: str = "cmd+shift+space" if sys.platform == "darwin" else "ctrl+space"
    model: str = "base"
    language: str = "auto"
    device: str = "auto"
    compute_type: str = "int8"
    sample_rate: int = 16_000
    auto_paste: bool = True
    punctuation: bool = True


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self._default_path()

    @staticmethod
    def _default_path() -> Path:
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "Voxen"
        else:
            base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Voxen"
        return base / "config.json"

    def _load_path(self) -> Path:
        if self.path.exists() or sys.platform != "darwin":
            return self.path
        legacy_path = Path.home() / "Voxen" / "config.json"
        return legacy_path if legacy_path.exists() else self.path

    def load(self) -> AppConfig:
        try:
            values = json.loads(self._load_path().read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return AppConfig()
        if not isinstance(values, dict):
            return AppConfig()
        version = values.get("version", 0)
        if type(version) is not int or version > CONFIG_VERSION:
            return AppConfig()
        defaults = asdict(AppConfig())
        for key, default in defaults.items():
            value = values.get(key, default)
            if type(value) is type(default) and self._is_valid_value(key, value):
                defaults[key] = value
        return AppConfig(**defaults)

    @staticmethod
    def _is_valid_value(key: str, value: object) -> bool:
        validator = _FIELD_VALIDATORS.get(key)
        return validator is None or validator(value)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        values = {"version": CONFIG_VERSION, **asdict(config)}
        payload = json.dumps(values, indent=2, ensure_ascii=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
