from voxen.stt import ModelConfig, ModelManager
import pytest


class FakeEngine:
    created = []

    def __init__(self, model: str, device: str, compute_type: str) -> None:
        self.settings = (model, device, compute_type)
        self.loaded = False
        self.unloaded = False
        self.created.append(self)

    def load(self) -> None:
        self.loaded = True

    def transcribe(self, _audio, language: str) -> str:
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