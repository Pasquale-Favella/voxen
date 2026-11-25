# Build Voxen

[Back to Voxen](../README.md)

PyInstaller builds for the host OS. Build on Windows for Windows, macOS for macOS and Linux for Linux. Use Python 3.11–3.13.

## Windows

```powershell
.\scripts\build-windows.ps1
```

The script creates `dist\Voxen\`. With Inno Setup installed, it builds `dist\installer\Voxen-Setup-<version>.exe`; otherwise it produces a portable ZIP.

## macOS

```bash
./scripts/build-macos.sh
```

Outputs `dist/Voxen.app` and `dist/Voxen-macos.dmg`.

## Linux x86-64 (X11)

Initial target: Ubuntu 22.04+ x86-64 with X11. The frozen executable includes Python and the speech engines, but uses host graphics/audio libraries. Older distributions are not guaranteed to work.

Install the DEB from the release assets (replace VERSION):

```bash
sudo apt install ./voxen_VERSION_amd64.deb
voxen
```

Or use the AppImage:

```bash
sudo apt install libportaudio2 xclip
chmod +x Voxen-VERSION-x86_64.AppImage
./Voxen-VERSION-x86_64.AppImage
```

If FUSE is unavailable, use `APPIMAGE_EXTRACT_AND_RUN=1 ./Voxen-VERSION-x86_64.AppImage`. The AppImage needs the usual X11 and audio libraries on the host. Neither package requires an installed Python interpreter.

Voxen requires an X11 session for global shortcuts and clipboard paste. Native Wayland is rejected. The dashboard minimizes to the taskbar instead of relying on a desktop-specific tray service. Pause / Resume and Quit are in the … menu. Linux clipboard restoration is plain text only.

To build locally (Ubuntu):

```bash
sudo apt install python3-venv python3-tk libportaudio2 xclip xvfb xauth file desktop-file-utils squashfs-tools curl
curl -fL https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage -o appimagetool
echo 'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0  appimagetool' | sha256sum -c -
chmod +x appimagetool
APPIMAGETOOL="$PWD/appimagetool" bash scripts/build-linux.sh
```

Use a supported Python 3.11–3.13 interpreter for the virtual environment. Outputs: `dist/voxen_<version>_amd64.deb` and `dist/Voxen-<version>-x86_64.AppImage`. The packaging job runs on PRs, tags and manual dispatch and smoke-tests both packages under Xvfb. Physical microphones and interactive desktop sessions require real-machine validation.

## Assets and validation

The build regenerates transparent light/dark PNGs and system ICO/ICNS icons from `assets/voxen-mark.svg`. The dashboard follows the selected appearance; system artwork uses a contrast keyline.

```bash
python -m pip install -e ".[dev]"
python scripts/create_assets.py
python -m ruff check src tests scripts
python -m pytest -q
```

On Linux CI, `xvfb-run -a python -m pytest -q` also exercises real Tk widgets. The dedicated model job downloads and validates Parakeet, transcribes a speech fixture and reloads it offline.

The standard GitHub Actions workflow packages builds on version tags or manual dispatch. Version metadata in `pyproject.toml`, `src/voxen/__init__.py` and `installer/Voxen.iss` must agree before release. Run `python scripts/check_release_version.py` to verify.
