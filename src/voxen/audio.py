from __future__ import annotations

from collections import deque
from threading import Lock


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
        self._lock = Lock()

    @property
    def level(self) -> float:
        with self._lock:
            return self._level

    def start(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Installa sounddevice e numpy per acquisire il microfono.") from exc

        blocksize = max(1, self.sample_rate // 50)

        def callback(indata, _frames, _time, status) -> None:
            del status
            block = np.array(indata[:, 0], dtype=np.float32, copy=True)
            with self._lock:
                self._level = min(1.0, float(np.sqrt(np.mean(block * block)) * 6))
                self._pre_roll.append(block)
                if self._recording:
                    self._frames.append(block)

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=blocksize,
            callback=callback,
        )
        self._stream.start()

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
