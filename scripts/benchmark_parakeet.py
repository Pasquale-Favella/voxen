"""Measure STT latency, throughput, process RSS and transcription accuracy.

Install the dev and parakeet extras. Run each model in a fresh process.
Pass --wav with real speech and matching --reference UTF-8 text files.
The first load may download weights; the second measures cached cold load.
RSS is sampled at 20 ms intervals, so very brief peaks may be missed.
"""

from __future__ import annotations

import argparse
import re
import statistics
import time
import wave
from pathlib import Path
from threading import Event, Thread

import numpy as np
import psutil

from voxen.config import SUPPORTED_MODELS
from voxen.stt import PARAKEET_MODEL, ModelConfig, ModelManager, models_root


def _synthetic(seconds: float, sample_rate: int) -> np.ndarray:
    samples = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    return (0.05 * np.sin(2 * np.pi * 220 * samples)).astype(np.float32)


def _read_wav(path: Path, sample_rate: int) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getcomptype() != "NONE":
            raise ValueError(f"{path}: expected mono 16-bit PCM WAV")
        raw = handle.readframes(handle.getnframes())
        source_rate = handle.getframerate()
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if not samples.size:
        raise ValueError(f"{path}: empty audio")
    if source_rate == sample_rate:
        return samples
    count = max(1, round(len(samples) * sample_rate / source_rate))
    return np.interp(np.arange(count) * source_rate / sample_rate, np.arange(len(samples)), samples).astype(np.float32)


def _disk_size(model: str) -> str:
    if model != PARAKEET_MODEL:
        return "n/a (shared HF cache)"
    root = models_root()
    total = sum(
        path.stat().st_size
        for directory in (root / PARAKEET_MODEL, root / "silero-vad")
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file()
    )
    return f"{total / (1024**2):.1f} MiB"


def _distance(reference, hypothesis) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def _error_rates(reference: str, hypothesis: str) -> tuple[float, float]:
    reference, hypothesis = _normalize(reference), _normalize(hypothesis)
    words = reference.split()
    chars = reference.replace(" ", "")
    if not words:
        raise ValueError("Reference must contain words")
    return _distance(words, hypothesis.split()) / len(words), _distance(chars, hypothesis.replace(" ", "")) / len(chars)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=PARAKEET_MODEL)
    parser.add_argument("--wav", nargs="+", type=Path, default=[], help="Mono 16-bit PCM WAV files")
    parser.add_argument("--reference", nargs="+", type=Path, default=[], help="Matching UTF-8 reference transcripts")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1 or args.seconds <= 0:
        parser.error("--runs and --seconds must be positive")
    if args.reference and len(args.reference) != len(args.wav):
        parser.error("Supply one reference per WAV")
    samples = [_read_wav(path, 16_000) for path in args.wav] or [_synthetic(args.seconds, 16_000)]
    manager = ModelManager()
    config = ModelConfig(args.model, "cpu", "int8")
    process = psutil.Process()
    baseline = process.memory_info().rss
    peak = [baseline]
    stop = Event()

    def monitor() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], process.memory_info().rss)
            stop.wait(0.02)

    thread = Thread(target=monitor, daemon=True)
    thread.start()
    try:
        start = time.perf_counter()
        manager.warm(config)
        first_load = time.perf_counter() - start
        manager.unload()
        start = time.perf_counter()
        manager.warm(config)
        cached_load = time.perf_counter() - start
        # An inference warm-up is not included in the measurements.
        manager.transcribe(samples[0], config)
        latencies = []
        transcripts = []
        for audio in samples:
            for _ in range(args.runs):
                start = time.perf_counter()
                transcript = manager.transcribe(audio, config)
                latencies.append(time.perf_counter() - start)
            transcripts.append(transcript)
        peak[0] = max(peak[0], process.memory_info().rss)
    finally:
        stop.set()
        thread.join()
        manager.unload()

    total_audio_seconds = sum(len(audio) for audio in samples) / 16_000 * args.runs
    rtfx = total_audio_seconds / sum(latencies)
    print(f"model:                {args.model}")
    print(f"first load (may download): {first_load:.3f} s")
    print(f"cached reload:        {cached_load:.3f} s")
    print(f"warm latency p50/p95: {statistics.median(latencies):.3f}/{np.percentile(latencies, 95):.3f} s (n={len(latencies)})")
    print(f"RTFx:                 {rtfx:.2f}")
    print(f"baseline RSS:         {baseline / (1024**2):.1f} MiB")
    print(f"peak sampled RSS:     {peak[0] / (1024**2):.1f} MiB")
    print(f"model on disk:        {_disk_size(args.model)}")
    if not args.wav:
        print("Synthetic timing only: not an accuracy benchmark (VAD may skip the tone).")
    for index, path in enumerate(args.wav):
        print(f"{path}: {transcripts[index]}")
        if args.reference:
            wer, cer = _error_rates(args.reference[index].read_text(encoding="utf-8"), transcripts[index])
            print(f"  normalized WER: {wer:.2%}; CER: {cer:.2%}")


if __name__ == "__main__":
    main()
