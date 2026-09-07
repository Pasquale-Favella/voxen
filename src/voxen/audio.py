from __future__ import annotations

import logging
from collections import deque
from threading import Lock

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Captures mono 16 kHz audio and retains a short pre-roll window."""

    def __init__(self, sample_rate: int = 16_000, preroll_ms: int = 500) -> None:
        self.sample_rate = sample_rate
        self.preroll_ms = preroll_ms
        self._stream = None
        self._pre_roll: deque[object] = deque(maxlen=max(1, preroll_ms // 20))
        self._recording = False
        self._frames: list[object] = []
        self._level = 0.0
        self._last_status: str | None = None
        self._lock = Lock()

    @property
    def level(self) -> float:
        with self._lock:
            return self._level

    @property
    def last_status(self) -> str | None:
        with self._lock:
            return self._last_status

    def start(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Installa sounddevice e numpy per acquisire il microfono.") from exc

        blocksize = max(1, self.sample_rate // 50)

        def callback(indata, _frames, _time, status) -> None:
            block = np.array(indata[:, 0], dtype=np.float32, copy=True)
            self._handle_block(block, status, np)

        stream = None
        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=blocksize,
                callback=callback,
            )
            stream.start()
            self._stream = stream
        except Exception as exc:
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass
            self._stream = None
            raise RuntimeError(f"Impossibile avviare il microfono: {exc}") from exc

    def _handle_block(self, block, status=None, numpy_module=None) -> None:
        if status:
            status_message = str(status)
            logger.warning("Audio input status: %s", status_message)
            with self._lock:
                self._last_status = status_message
        with self._lock:
            if numpy_module is None:
                import numpy as np

                numpy_module = np
            self._level = min(1.0, float(numpy_module.sqrt(numpy_module.mean(block * block)) * 6))
            self._pre_roll.append(block)
            if self._recording:
                self._frames.append(block)

    def begin(self) -> None:
        with self._lock:
            self._frames = list(self._pre_roll)
            self._recording = True

    def end(self):
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Installa numpy per elaborare l'audio.") from exc
        with self._lock:
            self._recording = False
            frames = self._frames
            self._frames = []
            self._level = 0.0
        if not frames:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(frames)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
