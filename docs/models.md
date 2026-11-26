# Models and benchmarks

[Back to Voxen](../README.md)

## Local inference

Parakeet TDT v3 runs on CPU using the INT8 ONNX export and onnx-asr. Whisper Tiny, Base and Small use CTranslate2 through Faster Whisper, with CPU or CUDA depending on the selected device and available runtime. Existing saved model selections are preserved.

The first model load may download weights. Parakeet files are pinned and validated with SHA-256 before opening the ONNX sessions offline. Missing or corrupt files are repaired individually. Silero VAD segments speech; if unavailable, fixed 20-second chunks are used. Recognition starts when the shortcut is released.

| Configuration | Path |
| :--- | :--- |
| Windows | `%LOCALAPPDATA%\Voxen\config.json` |
| macOS | `~/Library/Application Support/Voxen/config.json` |
| Linux | `$XDG_CONFIG_HOME/voxen/config.json` (default `~/.config/voxen/config.json`) |

On Windows/macOS, Parakeet uses a `models` subdirectory alongside the config. On Linux it uses `$XDG_DATA_HOME/voxen/models` (default `~/.local/share/voxen/models`); logs are under `$XDG_STATE_HOME/voxen/logs` (default `~/.local/state/voxen/logs`). Whisper uses its upstream shared model cache. Developers can remove the Parakeet cache via `ModelManager.delete_model("parakeet-tdt-v3")`; do not delete model files manually while inference is active.

Parakeet's language detection is automatic across 25 supported European languages. Its compute type is fixed by the INT8 export. Whisper supports selected languages, including Japanese, as well as automatic detection.

## Benchmarking

Install the development extra:

```bash
python -m pip install -e ".[dev]"
```

Use mono 16-bit PCM WAV recordings with matching UTF-8 reference transcripts. For example:

```bash
python scripts/benchmark_parakeet.py --model parakeet-tdt-v3 --wav it.wav en.wav mixed.wav --reference it.txt en.txt mixed.txt
python scripts/benchmark_parakeet.py --model base --wav it.wav en.wav mixed.wav --reference it.txt en.txt mixed.txt
```

Run each engine in a separate process. The script reports first load (potentially including a download), cached reload, warm p50/p95, real-time throughput, sampled process RSS, and normalized word/character error rates. Whisper disk size is not isolated from its shared cache. Synthetic audio is useful for timing smoke checks only, not accuracy.

No comparative performance or multilingual human-speech accuracy result is claimed here.

### Real-model smoke test

Set `VOXEN_PARAKEET_TEST_WAV` to a mono 16 kHz PCM WAV and `VOXEN_PARAKEET_TEST_EXPECTED` to a phrase expected in the recording, then run:

```bash
python -m pytest tests/test_parakeet_integration.py -q
```

The integration test verifies the actual weights, VAD and offline reload with application-level downloads blocked. It is not an OS-level network isolation test.

## Attribution and licenses

Voxen's MIT license does not relicense third-party model weights or libraries.

| Component | Attribution / license |
| :--- | :--- |
| Parakeet TDT v3 | [NVIDIA original model](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Parakeet ONNX export | [istupakov](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx) · converted to ONNX and quantized to INT8 |
| Silero VAD | [ONNX distribution and license](https://huggingface.co/istupakov/silero-vad-onnx) · [upstream](https://github.com/snakers4/silero-vad) |
| Whisper | [OpenAI Whisper](https://github.com/openai/whisper) · [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) and its converted model weights |

Consult each upstream distribution for its license and notices. The app downloads model weights separately rather than bundling them into its installers.
