from __future__ import annotations

import inspect
import logging
import os
import shutil
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
from typing import Protocol

logger = logging.getLogger(__name__)

PARAKEET_MODEL = "parakeet-tdt-v3"
PARAKEET_ASR_NAME = "nemo-parakeet-tdt-0.6b-v3"
PARAKEET_REVISION = "8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce"
PARAKEET_VAD_NAME = "silero"
PARAKEET_VAD_REVISION = "b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6"
PARAKEET_MODEL_FILES = ("config.json", "vocab.txt", "encoder-model.int8.onnx", "decoder_joint-model.int8.onnx")
PARAKEET_VAD_FILES = ("config.json", "silero_vad.onnx")
PARAKEET_CHUNK_SECONDS = 20
PARAKEET_MODELS = frozenset({PARAKEET_MODEL})


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


def is_parakeet_model(model: str) -> bool:
    return model in PARAKEET_MODELS


def default_engine_factory(model: str, device: str, compute_type: str) -> SpeechToTextEngine:
    if is_parakeet_model(model):
        return ParakeetEngine(model, device, compute_type)
    return FasterWhisperEngine(model, device, compute_type)


def models_root() -> Path:
    """Persistent directory for downloaded model weights."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Voxen"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Voxen"
    return base / "models"


def _validate_files(directory: Path, names: tuple[str, ...]) -> bool:
    return all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in names)


def _prepare_directory(directory: Path, names: tuple[str, ...]) -> None:
    """Remove an incomplete download so onnx-asr can fetch a clean snapshot."""
    if directory.exists() and not _validate_files(directory, names):
        shutil.rmtree(directory, ignore_errors=True)


def _chunks(samples, size: int) -> Iterator[object]:
    for start in range(0, len(samples), size):
        yield samples[start : start + size]


def _resolve_device(device: str) -> str:
    if device != "auto":
        return device
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def _resolve_compute_type(compute_type: str, resolved_device: str) -> str:
    # Plain "int8" is a CPU-optimized default; on CUDA it can fail or run
    # slowly. Map it to the CUDA-friendly equivalent unless the user
    # explicitly picked a CUDA-capable type.
    if resolved_device == "cuda" and compute_type == "int8":
        return "float16"
    return compute_type


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
            raise RuntimeError("Install faster-whisper to use local transcription.") from exc
        self.resolved_device = _resolve_device(self.device)
        self._model = WhisperModel(
            self.model_name,
            device=self.resolved_device,
            compute_type=_resolve_compute_type(self.compute_type, self.resolved_device),
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
                raise RuntimeError("Transcription cancelled.")
            parts.append(segment.text.strip())
        return " ".join(parts).strip()

    def unload(self) -> None:
        self._model = None


class ParakeetEngine:
    """Parakeet TDT v3 through the lightweight ``onnx-asr`` runtime.

    No PyTorch, NeMo or Transformers is involved: inference runs on ONNX
    Runtime with ``CPUExecutionProvider`` by default. The INT8 multilingual
    checkpoint detects the language automatically, so ``language`` is ignored.
    Recognition is buffered push-to-talk, not native streaming: Silero VAD
    (or a fixed-window fallback) segments long recordings internally.
    """

    def __init__(
        self,
        model: str = PARAKEET_MODEL,
        device: str = "auto",
        compute_type: str = "int8",
        cache_root: Path | None = None,
        use_vad: bool = True,
        sample_rate: int = 16_000,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.cache_root = Path(cache_root) if cache_root is not None else models_root()
        self.model_dir = self.cache_root / PARAKEET_MODEL
        self.vad_dir = self.cache_root / "silero-vad"
        self.use_vad = use_vad
        self.sample_rate = sample_rate
        self._model = None
        self._vad_enabled = False

    @staticmethod
    def _providers(device: str) -> list[str]:
        if device == "cuda":
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def load(self) -> None:
        try:
            import onnx_asr
        except ImportError as exc:
            raise RuntimeError(
                "Parakeet requires onnx-asr. Install it with: pip install -e '.[parakeet]'"
            ) from exc

        providers = self._providers(self.device)
        _prepare_directory(self.model_dir, PARAKEET_MODEL_FILES)
        # `revision` was added after onnx-asr 0.12.0; pin the weights when the
        # installed version supports it and rely on file validation otherwise.
        load_kwargs = {"path": self.model_dir, "quantization": "int8", "providers": providers}
        if "revision" in inspect.signature(onnx_asr.load_model).parameters:
            load_kwargs["revision"] = PARAKEET_REVISION
        model = onnx_asr.load_model(PARAKEET_ASR_NAME, **load_kwargs)
        if not _validate_files(self.model_dir, PARAKEET_MODEL_FILES):
            raise RuntimeError("Parakeet model download is incomplete. Delete the model cache and try again.")

        self._vad_enabled = False
        if self.use_vad:
            try:
                _prepare_directory(self.vad_dir, PARAKEET_VAD_FILES)
                vad_kwargs = {"path": self.vad_dir, "providers": providers}
                if "revision" in inspect.signature(onnx_asr.load_vad).parameters:
                    vad_kwargs["revision"] = PARAKEET_VAD_REVISION
                vad = onnx_asr.load_vad(PARAKEET_VAD_NAME, **vad_kwargs)
                model = model.with_vad(vad, max_speech_duration_s=PARAKEET_CHUNK_SECONDS)
                self._vad_enabled = True
            except Exception as exc:
                logger.warning("Parakeet VAD unavailable, using fixed segmentation: %s", exc)
        self._model = model

    def transcribe(self, audio: object, language: str = "auto", should_cancel: Callable[[], bool] | None = None) -> str:
        if self._model is None:
            self.load()
        if should_cancel is not None and should_cancel():
            raise RuntimeError("Transcription cancelled.")

        import numpy as np

        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            return ""

        if self._vad_enabled:
            parts = []
            for segment in self._model.recognize(samples, sample_rate=self.sample_rate):
                if should_cancel is not None and should_cancel():
                    raise RuntimeError("Transcription cancelled.")
                parts.append(segment.text if hasattr(segment, "text") else str(segment))
            return " ".join(part.strip() for part in parts if part.strip()).strip()

        parts = []
        chunk_samples = self.sample_rate * PARAKEET_CHUNK_SECONDS
        for chunk in _chunks(samples, chunk_samples):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("Transcription cancelled.")
            text = self._model.recognize(chunk, sample_rate=self.sample_rate)
            parts.append(text if isinstance(text, str) else str(text))
        return " ".join(part.strip() for part in parts if part.strip()).strip()

    def unload(self) -> None:
        self._model = None
        self._vad_enabled = False

    @classmethod
    def delete_cache(cls, cache_root: Path | None = None) -> None:
        root = Path(cache_root) if cache_root is not None else models_root()
        for directory in (root / PARAKEET_MODEL, root / "silero-vad"):
            shutil.rmtree(directory, ignore_errors=True)


class ModelManager:
    def __init__(
        self,
        engine_factory: SpeechToTextEngineFactory = default_engine_factory,
        max_load_attempts: int = 3,
        retry_delay: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_load_attempts < 1:
            raise ValueError("max_load_attempts must be at least 1.")
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
                raise RuntimeError("Model loading cancelled.")
            try:
                engine.load()
                if self._cancelled.is_set():
                    raise RuntimeError("Model loading cancelled.")
                return
            except Exception as exc:
                last_error = exc
                if self._cancelled.is_set():
                    raise RuntimeError("Model loading cancelled.") from exc
                if attempt == self._max_load_attempts:
                    raise RuntimeError(
                        f"Could not load the model after {attempt} attempts: {exc}"
                    ) from exc
                self._sleep(self._retry_delay * (2 ** (attempt - 1)))
        raise RuntimeError(f"Could not load the model: {last_error}") from last_error

    def get_engine(self, config: ModelConfig) -> SpeechToTextEngine:
        with self._lock:
            if self._cancelled.is_set():
                raise RuntimeError("Model loading cancelled.")
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
        # Snapshot the engine under lock, then transcribe without holding it:
        # holding the lock across the blocking transcription call would
        # serialize warm/transcribe and delay shutdown's unload. Shutdown
        # already defers unload until pending futures finish, so the snapshot
        # stays valid.
        engine = self.get_engine(config)
        cancelled = self._cancelled.is_set
        return engine.transcribe(audio, language, should_cancel=cancelled)

    def delete_model(self, model: str) -> None:
        """Unload an active engine and remove its cached weights on disk."""
        with self._lock:
            if self._config is not None and self._config.model == model:
                if self._engine is not None:
                    self._engine.unload()
                self._engine = None
                self._config = None
            if is_parakeet_model(model):
                ParakeetEngine.delete_cache()

    def unload(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.unload()
            self._engine = None
            self._config = None
