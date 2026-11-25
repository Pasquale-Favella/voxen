import hashlib
import io
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from voxen.stt import (
    PARAKEET_ASR_NAME,
    PARAKEET_MODEL,
    PARAKEET_REVISION,
    _ensure_files,
    FasterWhisperEngine,
    ModelConfig,
    ModelManager,
    ParakeetEngine,
    _resolve_compute_type,
    default_engine_factory,
)


class FakeEngine:
    created = []

    def __init__(self, model: str, device: str, compute_type: str) -> None:
        self.settings = (model, device, compute_type)
        self.loaded = False
        self.unloaded = False
        self.created.append(self)

    def load(self) -> None:
        self.loaded = True

    def transcribe(self, _audio, language: str, should_cancel=None) -> str:
        return f"{self.settings[0]}:{language}"

    def unload(self) -> None:
        self.unloaded = True


def test_model_manager_reuses_engine_for_the_same_configuration() -> None:
    FakeEngine.created = []
    manager = ModelManager(FakeEngine)
    config = ModelConfig("base", "cpu", "int8")

    first = manager.get_engine(config)
    second = manager.get_engine(config)

    assert first is second
    assert len(FakeEngine.created) == 1
    assert first.loaded is True


def test_model_manager_reloads_when_device_or_compute_type_changes() -> None:
    FakeEngine.created = []
    manager = ModelManager(FakeEngine)
    manager.get_engine(ModelConfig("base", "cpu", "int8"))
    first = FakeEngine.created[0]

    second = manager.get_engine(ModelConfig("base", "cuda", "float16"))

    assert second is not first
    assert first.unloaded is True
    assert second.settings == ("base", "cuda", "float16")


def test_model_manager_reloads_when_model_changes() -> None:
    FakeEngine.created = []
    manager = ModelManager(FakeEngine)

    first = manager.get_engine(ModelConfig("base"))
    second = manager.get_engine(ModelConfig("small"))

    assert second is not first
    assert first.unloaded is True
    assert second.settings == ("small", "auto", "int8")


def test_model_manager_keeps_previous_engine_when_reload_fails() -> None:
    FakeEngine.created = []

    class BrokenEngine(FakeEngine):
        def load(self) -> None:
            raise RuntimeError("new model unavailable")

    manager = ModelManager(FakeEngine, retry_delay=0, sleep=lambda _delay: None)
    first = manager.get_engine(ModelConfig("base"))
    manager._engine_factory = BrokenEngine

    with pytest.raises(RuntimeError, match="new model unavailable"):
        manager.get_engine(ModelConfig("small"))

    assert manager.get_engine(ModelConfig("base")) is first
    assert first.unloaded is False
    assert len(FakeEngine.created) == 2
    assert FakeEngine.created[1].unloaded is True


def test_model_manager_transcribes_using_the_requested_configuration() -> None:
    manager = ModelManager(FakeEngine)

    result = manager.transcribe([], ModelConfig("small"), "it")

    assert result == "small:it"


def test_model_manager_retries_failed_loads_with_backoff() -> None:
    attempts = []
    delays = []

    class FlakyEngine(FakeEngine):
        def load(self) -> None:
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("temporary download failure")
            super().load()

    manager = ModelManager(FlakyEngine, retry_delay=2, sleep=delays.append)

    engine = manager.get_engine(ModelConfig("base"))

    assert engine.loaded is True
    assert len(attempts) == 3
    assert delays == [2, 4]


def test_model_manager_reports_failure_after_retry_limit() -> None:
    class BrokenEngine(FakeEngine):
        def load(self) -> None:
            raise RuntimeError("download failed")

    manager = ModelManager(BrokenEngine, retry_delay=0, sleep=lambda _delay: None)

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        manager.get_engine(ModelConfig("base"))


def test_model_manager_does_not_start_after_cancellation() -> None:
    manager = ModelManager(FakeEngine)
    manager.cancel()

    with pytest.raises(RuntimeError, match="cancelled"):
        manager.get_engine(ModelConfig("base"))


class FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeWhisperModel:
    def __init__(self, segments) -> None:
        self._segments = segments

    def transcribe(self, _audio, language=None, vad_filter=True):
        return iter(self._segments), None


def test_faster_whisper_engine_joins_segment_text() -> None:
    engine = FasterWhisperEngine("base")
    engine._model = FakeWhisperModel([FakeSegment(" ciao "), FakeSegment("mondo ")])

    assert engine.transcribe([], "it") == "ciao mondo"


def test_faster_whisper_engine_stops_between_segments_when_cancelled() -> None:
    engine = FasterWhisperEngine("base")
    engine._model = FakeWhisperModel([FakeSegment("uno"), FakeSegment("due"), FakeSegment("tre")])
    calls = {"count": 0}

    def should_cancel() -> bool:
        calls["count"] += 1
        return calls["count"] >= 2

    with pytest.raises(RuntimeError, match="cancelled"):
        engine.transcribe([], "it", should_cancel=should_cancel)

    # cancellation was observed before the third segment was ever consumed
    assert calls["count"] == 2


def test_resolve_compute_type_maps_plain_int8_off_cuda() -> None:
    assert _resolve_compute_type("int8", "cuda") == "float16"
    assert _resolve_compute_type("int8", "cpu") == "int8"
    assert _resolve_compute_type("float16", "cuda") == "float16"
    assert _resolve_compute_type("int8_float16", "cuda") == "int8_float16"


MODEL_FILES = ("config.json", "vocab.txt", "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx", "nemo128.onnx")
VAD_FILES = ("silero_vad.onnx",)


class FakeOnnxAsrModel:
    def __init__(self, transcript: str = "ciao", segments=None) -> None:
        self.transcript = transcript
        self.segments = segments
        self.calls: list[tuple[object, int]] = []
        self.vad = None
        self.vad_options: dict = {}

    def recognize(self, waveform, sample_rate: int = 16_000):
        self.calls.append((waveform, sample_rate))
        return self.segments if self.segments is not None else self.transcript

    def with_vad(self, vad, **options):
        self.vad = vad
        self.vad_options = options
        return self


def _write_files(directory: Path, names: tuple[str, ...]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text("fake", encoding="utf-8")


def _install_fake_onnx_asr(monkeypatch, tmp_path, model, *, cached: bool, vad: bool = True, vad_fails: bool = False) -> dict:
    if cached:
        _write_files(tmp_path / PARAKEET_MODEL, MODEL_FILES)
        if vad:
            _write_files(tmp_path / "silero-vad", VAD_FILES)

    state: dict = {"loads": [], "vads": [], "offline": []}

    def ensure(directory, repository, revision, manifest, *, offline=False):
        state["offline"].append(Path(directory).exists()) if repository.endswith("parakeet-tdt-0.6b-v3-onnx") else None
        state.setdefault("downloads", []).append((repository, revision, tuple(manifest)))
        if vad_fails and repository.endswith("silero-vad-onnx"):
            raise RuntimeError("VAD download failed")
        _write_files(Path(directory), tuple(manifest))

    class Manager:
        def __init__(self, *, providers):
            self.providers = providers

        def create_asr(self, name, path, *, quantization, offline):
            state["loads"].append((name, Path(path), {"quantization": quantization, "providers": self.providers, "offline": offline}))
            return model

        def create_vad(self, name, path, *, offline):
            state["vads"].append((name, Path(path), {"offline": offline}))
            return types.SimpleNamespace(name=name)

    module = types.ModuleType("onnx_asr")
    loader = types.ModuleType("onnx_asr.loader")
    loader.Manager = Manager
    monkeypatch.setitem(sys.modules, "onnx_asr", module)
    monkeypatch.setitem(sys.modules, "onnx_asr.loader", loader)
    monkeypatch.setattr("voxen.stt._ensure_files", ensure)
    return state


def test_default_engine_factory_selects_engine_from_model_name() -> None:
    assert isinstance(default_engine_factory("base", "auto", "int8"), FasterWhisperEngine)
    assert isinstance(default_engine_factory(PARAKEET_MODEL, "auto", "int8"), ParakeetEngine)


def test_parakeet_engine_downloads_pinned_int8_model_with_cpu_provider(monkeypatch, tmp_path) -> None:
    model = FakeOnnxAsrModel()
    state = _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=False)

    engine = ParakeetEngine(cache_root=tmp_path, device="auto")
    engine.load()

    name, path, kwargs = state["loads"][0]
    assert name == PARAKEET_ASR_NAME
    assert path == tmp_path / PARAKEET_MODEL
    assert kwargs["quantization"] == "int8"
    assert kwargs["providers"] == ["CPUExecutionProvider"]
    assert kwargs["offline"] is True
    assert state["downloads"][0][1] == PARAKEET_REVISION
    assert state["offline"] == [False]
    assert engine._vad_enabled is True
    assert model.vad_options["max_speech_duration_s"] == 20


def test_parakeet_engine_loads_from_local_cache_without_network(monkeypatch, tmp_path) -> None:
    state = _install_fake_onnx_asr(monkeypatch, tmp_path, FakeOnnxAsrModel(), cached=True)

    ParakeetEngine(cache_root=tmp_path, device="cpu").load()

    assert state["offline"] == [True]
    assert len(state["vads"]) == 1


def test_parakeet_engine_repairs_incomplete_download(monkeypatch, tmp_path) -> None:
    _install_fake_onnx_asr(monkeypatch, tmp_path, FakeOnnxAsrModel(), cached=False)
    incomplete = tmp_path / PARAKEET_MODEL
    incomplete.mkdir()
    (incomplete / "config.json").write_text("partial", encoding="utf-8")

    ParakeetEngine(cache_root=tmp_path, device="cpu").load()

    assert all((incomplete / name).is_file() for name in MODEL_FILES)


def test_parakeet_engine_transcribes_numpy_array(monkeypatch, tmp_path) -> None:
    segments = [types.SimpleNamespace(text=" ciao "), types.SimpleNamespace(text="mondo")]
    model = FakeOnnxAsrModel(segments=segments)
    _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=True)
    engine = ParakeetEngine(cache_root=tmp_path, device="cpu")
    engine.load()

    result = engine.transcribe(np.zeros(1600, dtype=np.float32), "it")

    assert result == "ciao mondo"
    waveform, sample_rate = model.calls[0]
    assert len(waveform) == 1600
    assert sample_rate == 16_000


def test_parakeet_engine_falls_back_to_fixed_segmentation_without_vad(monkeypatch, tmp_path) -> None:
    model = FakeOnnxAsrModel(transcript="testo")
    _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=True, vad_fails=True)
    engine = ParakeetEngine(cache_root=tmp_path, device="cpu")
    engine.load()

    result = engine.transcribe(np.zeros(3 * 20 * 16_000, dtype=np.float32))

    assert engine._vad_enabled is False
    assert len(model.calls) == 3
    assert all(len(waveform) == 20 * 16_000 for waveform, _ in model.calls)
    assert result == "testo testo testo"


def test_parakeet_engine_respects_cancellation_between_segments(monkeypatch, tmp_path) -> None:
    model = FakeOnnxAsrModel(segments=[types.SimpleNamespace(text="uno"), types.SimpleNamespace(text="due")])
    _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=True)
    engine = ParakeetEngine(cache_root=tmp_path, device="cpu")
    engine.load()
    checks = {"count": 0}

    def should_cancel() -> bool:
        checks["count"] += 1
        return checks["count"] >= 2

    with pytest.raises(RuntimeError, match="cancelled"):
        engine.transcribe(np.zeros(16, dtype=np.float32), should_cancel=should_cancel)

    assert len(model.calls) == 1


def test_parakeet_engine_returns_empty_text_for_empty_audio(monkeypatch, tmp_path) -> None:
    model = FakeOnnxAsrModel()
    _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=True)
    engine = ParakeetEngine(cache_root=tmp_path, device="cpu")
    engine.load()

    assert engine.transcribe([]) == ""
    assert model.calls == []


def test_parakeet_engine_reports_missing_optional_extra(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "onnx_asr", None)
    monkeypatch.setitem(sys.modules, "onnx_asr.loader", None)

    with pytest.raises(RuntimeError, match="requires onnx-asr"):
        ParakeetEngine(cache_root=tmp_path).load()


def test_delete_cache_removes_model_and_vad_directories(monkeypatch, tmp_path) -> None:
    _install_fake_onnx_asr(monkeypatch, tmp_path, FakeOnnxAsrModel(), cached=True)
    assert (tmp_path / PARAKEET_MODEL).is_dir()
    assert (tmp_path / "silero-vad").is_dir()

    ParakeetEngine.delete_cache(tmp_path)

    assert not (tmp_path / PARAKEET_MODEL).exists()
    assert not (tmp_path / "silero-vad").exists()


def test_model_manager_delete_model_unloads_engine_and_cache(monkeypatch, tmp_path) -> None:
    model = FakeOnnxAsrModel()
    _install_fake_onnx_asr(monkeypatch, tmp_path, model, cached=True)
    deleted: list[str] = []
    monkeypatch.setattr(ParakeetEngine, "delete_cache", classmethod(lambda cls, root=None: deleted.append("parakeet")))
    manager = ModelManager()
    engine = manager.get_engine(ModelConfig(PARAKEET_MODEL))

    manager.delete_model(PARAKEET_MODEL)

    assert engine._model is None
    assert manager._engine is None
    assert deleted == ["parakeet"]

def test_verified_cache_repairs_corruption_and_reuses_files_offline(monkeypatch, tmp_path) -> None:
    payload = b"verified model"
    manifest = {"weights.onnx": hashlib.sha256(payload).hexdigest()}
    target = tmp_path / "weights.onnx"
    target.write_bytes(b"corrupt")
    urls = []

    def download(url, *, timeout):
        urls.append(url)
        return io.BytesIO(payload)

    monkeypatch.setattr("voxen.stt.urlopen", download)
    _ensure_files(tmp_path, "owner/model", "pinned", manifest)
    assert target.read_bytes() == payload
    assert urls == ["https://huggingface.co/owner/model/resolve/pinned/weights.onnx"]
    _ensure_files(tmp_path, "owner/model", "pinned", manifest, offline=True)
    assert len(urls) == 1
    target.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="Missing or corrupt"):
        _ensure_files(tmp_path, "owner/model", "pinned", manifest, offline=True)


def test_bad_download_does_not_replace_existing_file(monkeypatch, tmp_path) -> None:
    target = tmp_path / "weights.onnx"
    target.write_bytes(b"old")
    monkeypatch.setattr("voxen.stt.urlopen", lambda *args, **kwargs: io.BytesIO(b"bad"))
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        _ensure_files(tmp_path, "owner/model", "pinned", {"weights.onnx": hashlib.sha256(b"good").hexdigest()})
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]
