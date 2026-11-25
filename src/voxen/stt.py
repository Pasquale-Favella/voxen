from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
from typing import Protocol
from urllib.request import urlopen

logger = logging.getLogger(__name__)

PARAKEET_MODEL = "parakeet-tdt-v3"
PARAKEET_ASR_NAME = "nemo-parakeet-tdt-0.6b-v3"
PARAKEET_REVISION = "8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce"
PARAKEET_VAD_NAME = "silero"
PARAKEET_VAD_REVISION = "b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6"
# SHA-256 of the pinned upstream ONNX export (not the original NeMo weights).
PARAKEET_MANIFEST = {
    "config.json": "666903c76b9798caf2c210afd4f6cd60b08a8dbf9800ec8d7a3bc0d2148ac466",
    "vocab.txt": "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d",
    "encoder-model.int8.onnx": "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09",
    "decoder_joint-model.int8.onnx": "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70",
    "nemo128.onnx": "a9fde1486ebfcc08f328d75ad4610c67835fea58c73ba57e3209a6f6cf019e9f",
}
PARAKEET_VAD_MANIFEST = {
    "silero_vad.onnx": "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
}
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


def _matches_hash(path: Path, expected: str) -> bool:
    try:
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest() == expected
    except FileNotFoundError:
        return False


def _ensure_files(directory: Path, repository: str, revision: str, manifest: dict[str, str], *, offline: bool = False) -> None:
    """Validate cached files and atomically replace only missing or corrupt files."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in manifest.items():
        destination = directory / name
        if _matches_hash(destination, expected):
            continue
        if offline:
            raise RuntimeError(f"Missing or corrupt cached model file: {destination}")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=f".{name}.", suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                url = f"https://huggingface.co/{repository}/resolve/{revision}/{name}"
                with urlopen(url, timeout=60) as response:
                    shutil.copyfileobj(response, handle, length=1024 * 1024)
            if not _matches_hash(temporary, expected):
                raise RuntimeError(f"SHA-256 mismatch for {name}")
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


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
        offline: bool = False,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.cache_root = Path(cache_root) if cache_root is not None else models_root()
        self.model_dir = self.cache_root / PARAKEET_MODEL
        self.vad_dir = self.cache_root / "silero-vad"
        self.use_vad = use_vad
        self.sample_rate = sample_rate
        self.offline = offline
        self.resolved_device = None
        self._model = None
        self._vad_enabled = False

    def load(self) -> None:
        try:
            from onnx_asr.loader import Manager
        except ImportError as exc:
            raise RuntimeError(
                "Parakeet requires onnx-asr. Install it with: pip install -e '.[parakeet]'"
            ) from exc

        # The distributed extra contains CPU ONNX Runtime. Do not advertise
        # CUDA acceleration until a GPU build and its native dependencies exist.
        if self.device == "cuda":
            logger.warning("Parakeet uses CPU in this build; CUDA is not bundled.")
        providers = ["CPUExecutionProvider"]
        _ensure_files(self.model_dir, "istupakov/parakeet-tdt-0.6b-v3-onnx", PARAKEET_REVISION, PARAKEET_MANIFEST, offline=self.offline)
        manager = Manager(providers=providers)
        model = manager.create_asr(PARAKEET_ASR_NAME, self.model_dir, quantization="int8", offline=True)

        self._vad_enabled = False
        if self.use_vad:
            try:
                _ensure_files(self.vad_dir, "istupakov/silero-vad-onnx", PARAKEET_VAD_REVISION, PARAKEET_VAD_MANIFEST, offline=self.offline)
                vad = manager.create_vad(PARAKEET_VAD_NAME, self.vad_dir, offline=True)
                model = model.with_vad(vad, max_speech_duration_s=PARAKEET_CHUNK_SECONDS)
                self._vad_enabled = True
            except Exception as exc:
                logger.warning("Parakeet VAD unavailable, using fixed segmentation: %s", exc)
        self._model = model
        self.resolved_device = "cpu"

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
        self.resolved_device = None

    @classmethod
    def delete_cache(cls, cache_root: Path | None = None) -> None:
        root = Path(cache_root) if cache_root is not None else models_root()
        for directory in (root / PARAKEET_MODEL, root / "silero-vad"):
            if directory.exists():
                shutil.rmtree(directory)


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
        self._inference_lock = RLock()

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
        with self._inference_lock, self._lock:
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
        # Prevent engine replacement or cache deletion during native inference.
        with self._inference_lock:
            engine = self.get_engine(config)
            return engine.transcribe(audio, language, should_cancel=self._cancelled.is_set)

    def delete_model(self, model: str) -> None:
        """Unload an active engine and remove its cached weights on disk."""
        with self._inference_lock, self._lock:
            if self._config is not None and self._config.model == model:
                if self._engine is not None:
                    self._engine.unload()
                self._engine = None
                self._config = None
            if is_parakeet_model(model):
                ParakeetEngine.delete_cache()

    def unload(self) -> None:
        with self._inference_lock, self._lock:
            if self._engine is not None:
                self._engine.unload()
            self._engine = None
            self._config = None
