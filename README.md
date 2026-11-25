<p align="center">
	<img src="assets/voxen-mark.svg" alt="Voxen mark" width="132">
</p>

<h1 align="center">Voxen</h1>

<p align="center">
	Local-first voice dictation for Windows and macOS.
	<br>
	<strong>Hold. Speak. Release. Done.</strong>
</p>

<p align="center">
	Private by default. Fast by design. Ready wherever your cursor is.
</p>

## The idea

Voxen turns speech into text inside the application you are already using. It stays quiet in the tray or menu bar until you need it:

```text
HOLD HOTKEY  ->  SPEAK  ->  RELEASE  ->  TEXT IN THE ACTIVE APP
```

The audio is transcribed locally with NVIDIA Parakeet TDT v3 (the default) through the lightweight `onnx-asr` runtime, or Faster Whisper through CTranslate2. A network connection is needed for the first model download only; inference then remains on the machine.

## Quick start

Requirements: Python 3.11 or newer and a working microphone.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m voxen
```

Use `pythonw -m voxen` when you want to launch without a terminal window.

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m voxen
```

The first launch opens the Voxen dashboard and warms the selected model in the background. Parakeet uses CPU ONNX Runtime; with Whisper and `Auto` device selection, Voxen uses CUDA when CTranslate2 detects a CUDA-capable GPU, otherwise CPU.

## Parakeet (default)

Parakeet runs through [`onnx-asr`](https://github.com/istupakov/onnx-asr) using the pre-exported, INT8-quantized [multilingual ONNX weights](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx). No PyTorch, NeMo, Transformers, Docker, or external server is involved; inference uses ONNX Runtime with `CPUExecutionProvider` by default.

Parakeet is installed with Voxen and selected on a fresh configuration. Existing saved model choices are preserved; select `parakeet-tdt-v3` in the **Model** dropdown to switch. Notes:

- The pinned model files are SHA-256 validated and atomically repaired if necessary. The model is downloaded once into `%LOCALAPPDATA%\Voxen\models` (macOS: `~/Library/Application Support/Voxen/models`) and validated before use. Loads with intact cached files are fully offline.
- Silero VAD segments long recordings into short chunks; if VAD is unavailable, Voxen falls back to fixed 20-second windows. This is buffered push-to-talk transcription, not native streaming.
- Parakeet auto-detects among 25 European languages, so the **Language** setting has no effect. Punctuation and capitalization come from the model.
- Parakeet uses CPU ONNX Runtime in the current distribution. `Compute type` is unused because the INT8 weights are pinned. Whisper device selection is unchanged.
- Model attribution: [NVIDIA Parakeet TDT v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3), ONNX conversion and INT8 quantization by [istupakov](https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Silero VAD is [MIT licensed](https://huggingface.co/istupakov/silero-vad-onnx/blob/main/LICENSE.txt).
- Cached weights can be removed with `ModelManager.delete_model("parakeet-tdt-v3")`.

To compare engines or test Italian, English and mixed-language technical speech, see `scripts/benchmark_parakeet.py`. Install the dev extra as well. It reports first load (which may include download), cached reload, warm p50/p95 latency, real-time factor, sampled process RSS and model disk size. Use `--wav it.wav en.wav mixed.wav --reference it.txt en.txt mixed.txt` for transcripts and normalized WER/CER. Run each engine in a separate process.

## Appearance

Voxen follows the system application theme by default on Windows and macOS. Open the **…** menu → **Appearance** to select **System**, **Light**, or **Dark**. The choice applies immediately to the dashboard and floating recording pill and is saved independently of transcription settings. In System mode the app checks for OS appearance changes every two seconds. If the system preference is unavailable, Voxen retains the current palette (light at first launch).

## Daily flow

1. Place the cursor in any text field.
2. Hold the global shortcut and speak naturally.
3. Release the shortcut.
4. Voxen transcribes, cleans up the text, and pastes it into the active app.

| Platform | Default shortcut |
| --- | --- |
| Windows | `Ctrl+Space` |
| macOS | `Cmd+Shift+Space` |

The shortcut can be changed from the dashboard by pressing the desired key combination directly. The listening overlay shows the current state, elapsed time, and microphone level without taking over the screen.

## What is included

- Local speech-to-text with NVIDIA Parakeet TDT v3 via ONNX Runtime by default, and Faster Whisper as an alternative.
- Automatic detection of 25 European languages with Parakeet; Japanese and manual language selection with Whisper.
- Microphone access only while the global shortcut is held.
- Conservative cleanup for capitalization, whitespace, and final punctuation; existing punctuation is preserved.
- Clipboard-based paste with restoration of the previous clipboard contents. Windows and macOS use native clipboard formats when available, with a plain-text fallback.
- Tray/menu bar background mode with open, pause/resume, and quit actions.
- Persistent JSON settings for shortcut, model, language, and transcription options.

## Background mode

Closing the dashboard hides it; it does not stop Voxen. The listener, model, tray icon, and global shortcut continue running. The microphone is opened only while the global shortcut is held. Reopen the dashboard from the tray or menu bar.

On macOS, allow Voxen in **System Settings > Privacy & Security**:

- **Microphone** for audio capture;
- **Accessibility** for the global shortcut and paste;
- **Input Monitoring** if macOS requests it for global key events.

Voxen stores its configuration here:

```text
Windows: %LOCALAPPDATA%\Voxen\config.json
macOS:   ~/Library/Application Support/Voxen/config.json
```

## Build a distributable app

PyInstaller builds for the operating system it runs on, so build on the target platform.

### Windows

```powershell
.\scripts\build-windows.ps1
```

This creates a portable `dist\Voxen\` folder. If Inno Setup is installed, it also creates `dist\installer\Voxen-Setup-0.2.0.exe`; otherwise the script creates `dist\Voxen-windows.zip`.

### macOS

```bash
./scripts/build-macos.sh
```

This creates `dist/Voxen.app` and `dist/Voxen-macos.dmg`. The same builds can run through the GitHub Actions workflow on tags or manual dispatch.

The build pipeline regenerates `assets/voxen-mark.png` and `assets/voxen.ico` from `assets/voxen-mark.svg`, keeping the dashboard, tray, and application icon visually aligned.

## Project map

```text
src/voxen/           Application, audio, hotkey, tray, STT, and paste pipeline
assets/              SVG source mark and generated PNG/ICO assets
scripts/             Asset generation and Windows/macOS packaging commands
installer/           Optional Inno Setup definition for Windows
tests/               Focused unit tests for state, audio, config, hotkey, STT, clipboard, and text processing
```

## Test

```powershell
python -m pytest
```

## Scope

Voxen is intentionally small. History, profiles, continuous dictation, voice commands, LLM processing, and per-application rules are planned beyond the current MVP.
