"""Real-model test: set VOXEN_PARAKEET_TEST_WAV to a mono 16 kHz PCM WAV.

Set VOXEN_PARAKEET_TEST_EXPECTED to a word/phrase expected in the recording.
This test downloads the pinned model once, then reloads with downloads blocked.
Run with the parakeet extra installed; no synthetic model is substituted.
"""

import inspect
import os
import wave
from pathlib import Path

import numpy as np
import pytest

from voxen.stt import ParakeetEngine


def test_installed_onnx_runtime_api() -> None:
    pytest.importorskip("onnx_asr")
    runtime = pytest.importorskip("onnxruntime")
    from onnx_asr.loader import Manager

    assert "CPUExecutionProvider" in runtime.get_available_providers()
    assert "offline" in inspect.signature(Manager.create_asr).parameters
    assert "offline" in inspect.signature(Manager.create_vad).parameters


def test_real_parakeet_offline(monkeypatch, tmp_path) -> None:
    wav_path = os.getenv("VOXEN_PARAKEET_TEST_WAV")
    expected = os.getenv("VOXEN_PARAKEET_TEST_EXPECTED")
    if not wav_path or not expected:
        pytest.skip("Set VOXEN_PARAKEET_TEST_WAV and VOXEN_PARAKEET_TEST_EXPECTED")
    pytest.importorskip("onnx_asr")
    with wave.open(str(Path(wav_path)), "rb") as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, 16_000)
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    engine = ParakeetEngine(cache_root=tmp_path)
    try:
        engine.load()
        assert engine._vad_enabled, "Silero VAD failed to load"
        first = engine.transcribe(audio)
        assert expected.casefold() in first.casefold()
    finally:
        engine.unload()

    def no_download(*args, **kwargs):
        pytest.fail("Unexpected download during offline inference")

    monkeypatch.setattr("voxen.stt.urlopen", no_download)
    monkeypatch.setattr("socket.create_connection", no_download)
    offline = ParakeetEngine(cache_root=tmp_path, offline=True)
    try:
        offline.load()
        assert offline._vad_enabled
        assert offline.transcribe(audio) == first
    finally:
        offline.unload()
