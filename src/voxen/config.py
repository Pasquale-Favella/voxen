from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


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
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Voxen"
        self.path = path or base / "config.json"

    def load(self) -> AppConfig:
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return AppConfig()
        defaults = asdict(AppConfig())
        defaults.update({key: value for key, value in values.items() if key in defaults})
        return AppConfig(**defaults)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(config), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
