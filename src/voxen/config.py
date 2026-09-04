from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_VERSION = 1


@dataclass
class AppConfig:
    hotkey: str = "cmd+shift+space" if sys.platform == "darwin" else "ctrl+space"
    model: str = "base"
    language: str = "auto"
    device: str = "auto"
    compute_type: str = "int8"
    sample_rate: int = 16_000
    preroll_ms: int = 500
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
            if type(value) is type(default):
                defaults[key] = value
        return AppConfig(**defaults)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        values = {"version": CONFIG_VERSION, **asdict(config)}
        self.path.write_text(
            json.dumps(values, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
