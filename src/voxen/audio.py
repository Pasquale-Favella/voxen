from __future__ import annotations

import logging
from threading import Lock

logger = logging.getLogger(__name__)


class AudioRecorder:
    """Captures mono 16 kHz audio while a recording is active."""

    def __init__(self, sample_rate: int = 16_000) -> None:
        self.sample_rate = sample_rate
        self._stream = None
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

        with self._lock:
            if self._stream is not None:
                return
            self._last_status = None
            self._level = 0.0

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
            if self._recording:
                self._frames.append(block)

    def begin(self) -> None:
        with self._lock:
            self._frames = []
            self._recording = True

    def end(self):
        with self._lock:
            self._recording = False
            frames = self._frames
            self._frames = []
            self._level = 0.0
        self.close()
        with self._lock:
            self._level = 0.0
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Installa numpy per elaborare l'audio.") from exc
        if not frames:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(frames)

    def close(self) -> None:
        with self._lock:
            stream = self._stream
        if stream is None:
            return
        try:
            stream.stop()
        finally:
            try:
                stream.close()
            finally:
                with self._lock:
                    if self._stream is stream:
                        self._stream = None
