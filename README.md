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

The audio is transcribed locally with `faster-whisper`. A network connection is needed for the first model download only; inference then remains on the machine.

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

The first launch opens the Voxen dashboard and warms the selected Whisper model in the background. With `Auto` device selection, Voxen uses CUDA when CTranslate2 detects a CUDA-capable GPU; otherwise it uses the CPU.

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

- Local speech-to-text with `faster-whisper` and cached models.
- Italian, English, Japanese, French, German, Spanish, and automatic language detection.
- 500 ms audio pre-roll to avoid losing the beginning of a sentence.
- Conservative cleanup for capitalization, whitespace, and final punctuation; existing punctuation is preserved.
- Clipboard-based paste with restoration of the previous clipboard contents. Windows and macOS use native clipboard formats when available, with a plain-text fallback.
- Tray/menu bar background mode with open, pause/resume, and quit actions.
- Persistent JSON settings for shortcut, model, language, and transcription options.

## Background mode

Closing the dashboard hides it; it does not stop Voxen. The listener, microphone stream, model, tray icon, and global shortcut continue running. Reopen the dashboard from the tray or menu bar.

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

This creates a portable `dist\Voxen\` folder. If Inno Setup is installed, it also creates `dist\installer\Voxen-Setup-0.1.2.exe`; otherwise the script creates `dist\Voxen-windows.zip`.

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
