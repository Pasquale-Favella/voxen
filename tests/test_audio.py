import numpy as np
import types
import pytest

from voxen.audio import AudioRecorder


def test_audio_recorder_tracks_callback_status_and_audio() -> None:
    recorder = AudioRecorder(sample_rate=1000, preroll_ms=40)
    recorder._handle_block(np.ones(20, dtype=np.float32), "input overflow")

    recorder.begin()
    recorder._handle_block(np.zeros(20, dtype=np.float32), None)
    audio = recorder.end()

    assert recorder.last_status == "input overflow"
    assert audio.size == 40
    assert recorder.level == 0.0


def test_audio_recorder_normalizes_stream_start_failure(monkeypatch) -> None:
    class BrokenStream:
        def __init__(self, **_kwargs) -> None:
            self.closed = False

        def start(self) -> None:
            raise OSError("no input device")

        def close(self) -> None:
            self.closed = True

    stream_holder = {}

    def make_stream(**kwargs):
        stream = BrokenStream(**kwargs)
        stream_holder["stream"] = stream
        return stream

    fake_sounddevice = types.SimpleNamespace(InputStream=make_stream)
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)
    recorder = AudioRecorder()

    with pytest.raises(RuntimeError, match="Impossibile avviare il microfono"):
        recorder.start()

    assert recorder._stream is None
    assert stream_holder["stream"].closed is True