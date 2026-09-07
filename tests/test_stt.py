import pytest

from voxen.stt import FasterWhisperEngine, ModelConfig, ModelManager


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

    with pytest.raises(RuntimeError, match="dopo 3 tentativi"):
        manager.get_engine(ModelConfig("base"))


def test_model_manager_does_not_start_after_cancellation() -> None:
    manager = ModelManager(FakeEngine)
    manager.cancel()

    with pytest.raises(RuntimeError, match="annullato"):
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

    with pytest.raises(RuntimeError, match="annullat"):
        engine.transcribe([], "it", should_cancel=should_cancel)

    # cancellation was observed before the third segment was ever consumed
    assert calls["count"] == 2