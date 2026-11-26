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

Outputs `dist/Voxen.app` and `dist/Voxen-macos-arm64.dmg` or `dist/Voxen-macos-x86_64.dmg`, depending on the native Python architecture. Use a native Python interpreter, not Rosetta, for the target architecture. CI builds and verifies both on macOS 15 with actual Parakeet inference from the mounted DMG. Intel uses ONNX Runtime 1.23.2 because newer releases no longer provide Intel wheels. Other platforms keep their existing runtime resolution. macOS versions older than 15 are not yet validated. Ad-hoc signatures are verified; this is not Apple notarization.

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

Voxen requires an X11 session for global shortcuts and clipboard paste. Native Wayland is rejected with an explanation at startup. The dashboard minimizes to the taskbar instead of relying on a desktop-specific tray service. Pause / Resume and Quit are in the … menu. Linux clipboard restoration is plain text only.

To build locally (Ubuntu):

```bash
sudo apt install python3-venv python3-tk libportaudio2 xclip xvfb xauth file desktop-file-utils squashfs-tools curl
curl -fL https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage -o appimagetool
echo 'ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0  appimagetool' | sha256sum -c -
chmod +x appimagetool
APPIMAGETOOL="$PWD/appimagetool" bash scripts/build-linux.sh
```

Use a supported Python 3.11–3.13 interpreter for the virtual environment. Outputs: `dist/voxen_<version>_amd64.deb` and `dist/Voxen-<version>-x86_64.AppImage`. The packaging job runs on PRs, tags and manual dispatch and smoke-tests both packages under Xvfb. The CI also exercises real X11 shortcut events and plain-text clipboard paste in a virtual display. Physical microphones, window-manager behavior and interactive desktop sessions require real-machine validation.

## Assets and validation

The build regenerates transparent light/dark PNGs and system ICO/ICNS icons from `assets/voxen-waveform.svg`. The dashboard follows the selected appearance; system artwork uses a contrast keyline.

```bash
python -m pip install -e ".[dev]"
python scripts/create_assets.py
python -m ruff check src tests scripts
python -m pytest -q
```

On Linux CI, `xvfb-run -a python -m pytest -q` also exercises real Tk widgets. The dedicated model job downloads and validates Parakeet, transcribes a speech fixture and reloads it offline.

The standard GitHub Actions workflow packages builds on version tags or manual dispatch. Version metadata in `pyproject.toml`, `src/voxen/__init__.py` and `installer/Voxen.iss` must agree before release. Run `python scripts/check_release_version.py` to verify.

## Release integrity and signing

The tag-triggered release job stages the Windows EXE, both macOS DMGs, Linux DEB and AppImage (and optional Windows ZIP), generates `SHA256SUMS`, creates GitHub Artifact Attestations for the final bytes via Sigstore, verifies them, then publishes the release. The attestation associates the artifacts with the repository and tag-triggered workflow; it does not imply a platform-native code signature. Older releases may not include attestations.

Download the desired asset and `SHA256SUMS` from the same release. On Linux, check the downloaded files:

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

On macOS, use `shasum -a 256 <installer>`; on Windows PowerShell, use `Get-FileHash <installer> -Algorithm SHA256` and compare with the matching line. A checksum alone does not authenticate the publisher.

For cryptographic provenance, install a recent [GitHub CLI](https://cli.github.com/) and verify each downloaded file against this repository and its release tag:

```bash
gh attestation verify ./Voxen-macos-arm64.dmg --repo Pasquale-Favella/voxen --source-ref refs/tags/vVERSION
gh attestation verify ./SHA256SUMS --repo Pasquale-Favella/voxen --source-ref refs/tags/vVERSION
```

Replace `vVERSION` with the actual tag (e.g. `v0.2.1` once published). The same verification applies to EXE, DEB, AppImage and ZIP files.

### Native platform signing — not yet configured

- Windows: Authenticode for the application EXE and final installer, with a trusted timestamp. [SignPath Foundation](https://signpath.org/) offers free signing for eligible open-source projects, subject to approval.
- macOS: Developer ID Application signing, hardened runtime, Apple notarization and stapling. An Apple Developer Program account and signing identity are needed.
- Linux: GitHub provenance attestation covers both packages. Embedded AppImage GPG signatures or a signed APT repository can be added later if a stable project signing identity is established.

The keyless workflow does not require private signing keys and does not remove Windows SmartScreen or macOS Gatekeeper prompts. Do not commit certificates, signing keys or API tokens. Native signing must happen before the final checksum and attestation step. Published release assets must not be silently replaced; issue a new version for changes.


### macOS input regression coverage

macOS uses a listen-only Quartz keyboard tap on the main run loop, a Cocoa status item and direct Command+V Quartz events. No Carbon input-source lookup runs in a background listener. Grant Input Monitoring for shortcuts and Accessibility for paste; use the dashboard overflow menu to retry the shortcut after granting permission. The macOS bundle identifier is now stable (`io.github.pasquale-favella.voxen`), so previously granted permissions may need to be granted again.

The packaged runtime smoke test starts the actual macOS services with model warm-up stubbed (inference is tested independently), checks the menu bar item and event tap or explicit permission-denial path, and exercises synthetic Quartz key events without injecting global input. Both release DMGs are also launched on macOS 26 runners before publication. Hosted CI cannot guarantee a TCC-granted physical keyboard or microphone; interactive checks with actual permissions remain necessary.

### Single-instance desktop lifecycle

Normal launches acquire an OS-owned lock in the current user's Voxen configuration directory before creating Tk or starting audio/model services. A second launch sends a payload-free activation request and exits after acknowledgment; the primary restores its existing dashboard on the Tk thread. Requests coalesce, and if the primary exits before handling the request a contender can take ownership. The lock is released by the OS even after a process crash; the lock file is intentionally never deleted. No listening network port or external dependency is introduced. The scope is the configuration profile, not the entire machine. macOS Dock/Finder reopen events also restore the existing window. The diagnostic `--check-runtime` mode intentionally bypasses the production lock and uses a temporary profile.

CI exercises real cross-process contention, crash recovery and request acknowledgment on Windows, macOS and Linux; frozen smoke checks verify dashboard restoration on the original Tk instance. Foreground activation remains subject to OS window-manager focus policy.
