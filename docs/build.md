# Build Voxen

[Back to Voxen](../README.md)

PyInstaller builds for the host OS. Build on Windows for Windows and on macOS for macOS. Use Python 3.11–3.13.

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
