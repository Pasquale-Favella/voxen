from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, RLock
from typing import Protocol


@dataclass(frozen=True)
class ModelConfig:
    model: str
    device: str = "auto"
    compute_type: str = "int8"


class SpeechToTextEngine(Protocol):
    def load(self) -> None:
        ...

    def transcribe(self, audio: object, language: str, should_cancel: Callable[[], bool] | None = None) -> str:
        ...

    def unload(self) -> None:
        ...


SpeechToTextEngineFactory = Callable[[str, str, str], SpeechToTextEngine]


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except (ImportError, AttributeError, RuntimeError):
        return "cpu"


class FasterWhisperEngine:
    def __init__(self, model: str, device: str = "auto", compute_type: str = "int8") -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.resolved_device = None
        self._model = None

    def load(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Installa faster-whisper per usare la trascrizione locale.") from exc
        self.resolved_device = _resolve_device(self.device)
        self._model = WhisperModel(
            self.model_name,
            device=self.resolved_device,
            compute_type=self.compute_type,
        )

    def transcribe(self, audio: object, language: str = "auto", should_cancel: Callable[[], bool] | None = None) -> str:
        if self._model is None:
            self.load()
        segments, _info = self._model.transcribe(
            audio,
            language=None if language == "auto" else language,
            vad_filter=True,
        )
        parts = []
        for segment in segments:
            if should_cancel is not None and should_cancel():
                raise RuntimeError("Trascrizione annullata.")
            parts.append(segment.text.strip())
        return " ".join(parts).strip()

    def unload(self) -> None:
        self._model = None


class ModelManager:
    def __init__(
        self,
        engine_factory: SpeechToTextEngineFactory = FasterWhisperEngine,
        max_load_attempts: int = 3,
        retry_delay: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_load_attempts < 1:
            raise ValueError("max_load_attempts deve essere almeno 1.")
        self._engine_factory = engine_factory
        self._max_load_attempts = max_load_attempts
        self._retry_delay = retry_delay
        self._sleep = sleep
        self._cancelled = Event()
        self._engine: SpeechToTextEngine | None = None
        self._config: ModelConfig | None = None
        self._lock = RLock()

    def cancel(self) -> None:
        self._cancelled.set()

    def _load(self, engine: SpeechToTextEngine) -> None:
        last_error = None
        for attempt in range(1, self._max_load_attempts + 1):
            if self._cancelled.is_set():
                raise RuntimeError("Caricamento modello annullato.")
            try:
                engine.load()
                if self._cancelled.is_set():
                    raise RuntimeError("Caricamento modello annullato.")
                return
            except Exception as exc:
                last_error = exc
                if self._cancelled.is_set():
                    raise RuntimeError("Caricamento modello annullato.") from exc
                if attempt == self._max_load_attempts:
                    raise RuntimeError(
                        f"Impossibile caricare il modello dopo {attempt} tentativi: {exc}"
                    ) from exc
                self._sleep(self._retry_delay * (2 ** (attempt - 1)))
        raise RuntimeError(f"Impossibile caricare il modello: {last_error}") from last_error

    def get_engine(self, config: ModelConfig) -> SpeechToTextEngine:
        with self._lock:
            if self._cancelled.is_set():
                raise RuntimeError("Caricamento modello annullato.")
            if self._engine is not None and self._config == config:
                return self._engine

            new_engine = self._engine_factory(
                config.model,
                config.device,
                config.compute_type,
            )
            try:
                self._load(new_engine)
            except Exception:
                new_engine.unload()
                raise

            old_engine = self._engine
            self._engine = new_engine
            self._config = config
            if old_engine is not None:
                old_engine.unload()
            return new_engine

    def warm(self, config: ModelConfig) -> None:
        self.get_engine(config)

    def transcribe(self, audio, config: ModelConfig, language: str = "auto") -> str:
        with self._lock:
            engine = self.get_engine(config)
            return engine.transcribe(audio, language, should_cancel=self._cancelled.is_set)

    def unload(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.unload()
            self._engine = None
            self._config = None
