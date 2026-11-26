<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/voxen-mark-dark.svg">
    <img src="assets/voxen-mark.svg" alt="Voxen" width="112">
  </picture>

  <h1>Voxen</h1>

  <p><strong>Your voice, anywhere you type.</strong></p>
  <p>Local-first voice dictation for Windows, macOS and Linux (X11).<br>
  Hold a shortcut, speak naturally, and release to type.</p>

  <p>
    <a href="https://github.com/Pasquale-Favella/voxen/releases/latest"><img src="https://img.shields.io/github/v/release/Pasquale-Favella/voxen?style=flat-square&color=52525b&label=release" alt="Latest release"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-52525b?style=flat-square" alt="MIT license"></a>
    <a href="https://github.com/Pasquale-Favella/voxen/actions/workflows/build.yml"><img src="https://img.shields.io/github/actions/workflow/status/Pasquale-Favella/voxen/build.yml?branch=main&style=flat-square&label=build" alt="Build status"></a>
  </p>

  <p><a href="https://github.com/Pasquale-Favella/voxen/releases/latest"><strong>Download Voxen</strong></a> · <a href="#how-it-works">How it works</a> · <a href="#run-from-source">Develop</a></p>
</div>

<br>

Voxen is a small desktop utility that turns your voice into text in the app you're already using. No separate editor to open, no cloud transcription service, no account to create. It stays in the system tray, menu bar or minimized Linux window until you need it.

## How it works

<kbd>Hold</kbd> &nbsp; → &nbsp; <kbd>Speak</kbd> &nbsp; → &nbsp; <kbd>Release</kbd> &nbsp; → &nbsp; **Text at your cursor**

1. Put your cursor in a text field — a message, document, terminal or editor.
2. Hold your shortcut and speak. A compact floating pill shows the audio level and elapsed time.
3. Release the shortcut. Voxen transcribes locally and, by default, pastes the result into the focused application.

| Windows / Linux (X11) | macOS |
| :--- | :--- |
| <kbd>Ctrl</kbd> + <kbd>Space</kbd> | <kbd>Cmd</kbd> + <kbd>Shift</kbd> + <kbd>Space</kbd> |

Change the shortcut in the dashboard. Closing the window hides Voxen on Windows/macOS or minimizes it on Linux, while the global shortcut remains available. On Windows/macOS, pause, reopen or quit from the tray/menu bar. On Linux, the window minimizes to the taskbar; Pause / Resume and Quit are in the … menu.

## Designed to stay out of your way

- **On-device recognition.** Parakeet TDT v3 INT8 is the default for new installations; Whisper is available as an alternative.
- **Private by design.** Audio and transcripts are processed on your machine. Model downloads require a connection; recognition works offline with the model cached.
- **A quiet interface.** A compact dashboard, a minimal recording pill, and light/dark appearance that follows your system by default.
- **Natural text.** Automatic language detection, conservative punctuation and capitalization cleanup, and clipboard-based paste with best-effort restoration of previous clipboard contents.
- **Your choice.** Configure the shortcut, recognition model, language where supported, automatic paste and final punctuation.

## Download

Get the latest published build from [GitHub Releases](https://github.com/Pasquale-Favella/voxen/releases/latest). The redesigned interface described here is available in the source tree and may not yet be in the latest published build.

| Platform | Package | Installation |
| :--- | :--- | :--- |
| Windows | `Voxen-Setup-<version>.exe` | Run the installer |
| macOS | `Voxen-macos.dmg` | Open the disk image and move Voxen to Applications |
| Linux x86-64 (X11) | `voxen_<version>_amd64.deb` / `Voxen-<version>-x86_64.AppImage` | Install the DEB or make the AppImage executable |

For releases produced by the attestation-enabled pipeline, see [how to verify installer provenance and SHA-256 checksums](docs/build.md#release-integrity-and-signing). Platform-native code signing is not yet configured.

On first launch, allow microphone access and wait for the selected model to download and load. On macOS, enable **Accessibility** in System Settings → Privacy & Security for global shortcuts and text injection; grant **Input Monitoring** if requested.

Linux packaging initially targets x86-64 X11 sessions on Ubuntu 22.04 or newer (other compatible distributions may work). Native Wayland global shortcuts and paste are not supported. See [Linux installation](docs/build.md#linux-x86-64-x11) for dependencies and launch instructions.

## Speech engines

| Engine | Runtime | Language | Device |
| :--- | :--- | :--- | :--- |
| **Parakeet TDT v3 INT8** (default) | ONNX Runtime via [onnx-asr](https://github.com/istupakov/onnx-asr) | Auto · 25 European languages | CPU |
| Whisper Tiny / Base / Small | [Faster Whisper](https://github.com/SYSTRAN/faster-whisper) · CTranslate2 | Auto or selected language | CPU / CUDA when available |

Parakeet does not require NeMo, PyTorch, Docker, Ollama or a separate inference server. Model files are pinned to specific revisions, checked against SHA-256 hashes and repaired atomically if corrupt. Silero VAD splits longer recordings into speech segments; fixed 20-second chunks are the fallback. Voxen uses buffered push-to-talk inference after release, not live streaming.

Existing saved model choices are preserved when upgrading. Parakeet detects language automatically, so its language selector is disabled. See the [model documentation](docs/models.md) for caching, attribution and benchmarking.

## Appearance

Open **… → Appearance** to choose **System**, **Light** or **Dark**. The preference applies immediately to the dashboard, brand mark and recording pill without restarting the recognition engine. System mode follows Windows/macOS appearance changes and Linux desktop portal preferences when available, checked every two seconds.

## Run from source

Requires Python **3.11–3.13**, a working microphone and Tk.

```bash
git clone https://github.com/Pasquale-Favella/voxen.git
cd voxen
python -m venv .venv
```

Activate the environment:

| Windows PowerShell | macOS / Linux |
| :--- | :--- |
| ` .\.venv\Scripts\Activate.ps1 ` | `source .venv/bin/activate` |

```bash
python -m pip install -e .
python -m voxen
```

For development, testing, benchmarking and packaging, install `python -m pip install -e ".[dev]"` instead. On Windows, `pythonw -m voxen` launches without a terminal window.

## Development

Voxen separates the UI and system integrations from the dictation lifecycle and speech engine.

```text
Global hotkey
     │
     ▼
Dictation service ── Audio recorder
     │
     ▼
Speech engine ────── Parakeet / Whisper
     │
     ▼
Text processing ──── Clipboard / focused app
```

<details>
<summary>Project structure</summary>

```text
src/voxen/
  application/     Dictation service, ports and events
  domain/          State, hotkey combinations and text processing
  infrastructure/  Platform integration, resources, DPI and logging
  presentation/    Theme, widgets and recording pill
  stt.py           Speech engines, model cache and lifecycle
  app.py           Desktop composition and event handling
assets/            Vector identity and generated icons
scripts/           Build, release checks and benchmarks
installer/         Windows installer definition
tests/             Unit, UI and integration tests
```

</details>

```bash
python -m ruff check src tests scripts
python -m pytest -q
```

The real-model integration test is exercised in CI. For the local test and benchmark commands, see [models and benchmarks](docs/models.md). For packaging, see the [build guide](docs/build.md).

## Contributing

Bug reports and focused pull requests are welcome. Open an [issue](https://github.com/Pasquale-Favella/voxen/issues) with your OS, Voxen version, selected model and reproduction steps. Avoid including private audio or transcript content.

Voxen deliberately focuses on one task: turning speech into text at the cursor. History, continuous dictation, voice commands and LLM-based processing are outside the current implementation.

## License

Voxen's own source code and artwork are available under the [MIT License](LICENSE). Third-party models and libraries retain their respective licenses, including NVIDIA Parakeet under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See [model attribution](docs/models.md#attribution-and-licenses).

<div align="center">
  <sub>Speak naturally. Keep typing.</sub>
</div>
