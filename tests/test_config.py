import json
from pathlib import Path

import pytest

import voxen.config as config_module
from voxen.config import CONFIG_VERSION, AppConfig, ConfigStore


def test_config_round_trip(tmp_path) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    config = AppConfig(model="small", language="it", auto_paste=False)

    store.save(config)

    assert store.load() == config
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == CONFIG_VERSION


def test_config_uses_defaults_for_invalid_or_unknown_values(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"model": "tiny", "unknown": True}), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config.model == "tiny"
    assert config.language == AppConfig().language
    assert not hasattr(config, "unknown")


def test_config_reads_legacy_file_without_version(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"model": "tiny"}), encoding="utf-8")

    assert ConfigStore(path).load().model == "tiny"


def test_config_rejects_future_version(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"version": CONFIG_VERSION + 1, "model": "tiny"}), encoding="utf-8")

    assert ConfigStore(path).load() == AppConfig()


def test_config_uses_defaults_for_malformed_json(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")

    assert ConfigStore(path).load() == AppConfig()


def test_config_uses_defaults_when_json_is_not_an_object(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[]", encoding="utf-8")

    assert ConfigStore(path).load() == AppConfig()


def test_config_ignores_values_with_wrong_types(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sample_rate": "fast", "auto_paste": 1}), encoding="utf-8")

    config = ConfigStore(path).load()

    assert config.sample_rate == AppConfig().sample_rate
    assert config.auto_paste is AppConfig().auto_paste


def test_config_ignores_semantically_invalid_values(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({
            "model": "unknown",
            "language": "xx",
            "sample_rate": 0,
            "preroll_ms": -1,
        }),
        encoding="utf-8",
    )

    config = ConfigStore(path).load()
    defaults = AppConfig()

    assert config.model == defaults.model
    assert config.language == defaults.language
    assert config.sample_rate == defaults.sample_rate
    assert config.preroll_ms == defaults.preroll_ms


def test_config_uses_application_support_on_macos(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert ConfigStore().path == tmp_path / "Library" / "Application Support" / "Voxen" / "config.json"


def test_config_reads_legacy_macos_location(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    legacy_path = tmp_path / "Voxen" / "config.json"
    legacy_path.parent.mkdir()
    legacy_path.write_text(json.dumps({"model": "tiny"}), encoding="utf-8")

    assert ConfigStore().load().model == "tiny"


def test_config_save_does_not_leave_a_partial_file_if_writing_fails(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    store = ConfigStore(path)
    store.save(AppConfig(model="small"))

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(config_module.os, "replace", boom)

    with pytest.raises(OSError):
        store.save(AppConfig(model="tiny"))

    assert ConfigStore(path).load().model == "small"
    assert list(tmp_path.glob(".config-*.tmp")) == []