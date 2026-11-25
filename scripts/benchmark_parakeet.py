"""Compare Voxen STT engines (cold start, warm latency, RTFx, RAM, disk size).

Examples:

    python scripts/benchmark_parakeet.py --model parakeet-tdt-v3
    python scripts/benchmark_parakeet.py --model parakeet-tdt-v3 --wav it.wav en.wav mixed.wav
    python scripts/benchmark_parakeet.py --model small

Pass real WAVs for Italian, English and mixed-language technical speech to test
accuracy; without --wav the script uses a synthetic tone for timing only.

RTFx = audio seconds / processing seconds (higher is better). Peak RAM is the
Python heap measured by tracemalloc; it excludes native ONNX/CTranslate2
allocations, so treat it as a lower bound.
"""

from __future__ import annotations

import argparse
import statistics
import time
import tracemalloc
import wave
from pathlib import Path

import numpy as np

from voxen.config import SUPPORTED_MODELS
from voxen.stt import PARAKEET_MODEL, ModelConfig, ModelManager, models_root


def _synthetic(seconds: float, sample_rate: int) -> np.ndarray:
    samples = np.arange(int(seconds * sample_rate), dtype=np.float32) / sample_rate
    return (0.05 * np.sin(2 * np.pi * 220 * samples)).astype(np.float32)


def _read_wav(path: Path, sample_rate: int) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
        source_rate = handle.getframerate()
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if source_rate == sample_rate:
        return samples
    count = int(len(samples) * sample_rate / source_rate)
    return np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples).astype(np.float32)


def _disk_size(model: str) -> str:
    if model != PARAKEET_MODEL:
        return "n/a (shared HF cache)"
    directory = models_root() / PARAKEET_MODEL
    if not directory.is_dir():
        return "not downloaded"
    total = sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
    return f"{total / (1024**2):.1f} MiB"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=SUPPORTED_MODELS, default=PARAKEET_MODEL)
    parser.add_argument("--wav", nargs="*", type=Path, default=[], help="16 kHz mono PCM WAV files")
    parser.add_argument("--seconds", type=float, default=5.0, help="synthetic audio duration")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    samples = [_read_wav(path, 16_000) for path in args.wav] or [_synthetic(args.seconds, 16_000)]
    manager = ModelManager()
    config = ModelConfig(args.model, "cpu", "int8")

    tracemalloc.start()
    start = time.perf_counter()
    manager.warm(config)
    cold_start = time.perf_counter() - start

    latencies = []
    for audio in samples:
        for _ in range(args.runs):
            start = time.perf_counter()
            manager.transcribe(audio, config)
            latencies.append(time.perf_counter() - start)
    peak_bytes = tracemalloc.get_traced_memory()[1]
    manager.unload()

    mean_latency = statistics.mean(latencies)
    rtf = (sum(len(audio) for audio in samples) / 16_000) / mean_latency
    print(f"model:            {args.model}")
    print(f"cold start:       {cold_start:.3f} s")
    print(f"warm latency:     {mean_latency:.3f} s (n={len(latencies)})")
    print(f"RTFx:             {rtf:.2f}")
    print(f"peak python RAM:  {peak_bytes / (1024**2):.1f} MiB")
    print(f"model on disk:    {_disk_size(args.model)}")


if __name__ == "__main__":
    main()
