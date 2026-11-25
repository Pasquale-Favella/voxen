"""Package the frozen Linux application as a DEB and an AppImage."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def main() -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("Linux packaging currently targets x86_64 only.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    tool = os.environ.get("APPIMAGETOOL") or shutil.which("appimagetool")
    if not tool:
        raise SystemExit("Set APPIMAGETOOL to the pinned executable (see docs/build.md).")
    appdir = DIST / "Voxen.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    usr = appdir / "usr"
    shutil.copytree(DIST / "Voxen", usr / "lib" / "voxen", symlinks=True)
    bin_dir = usr / "bin"
    bin_dir.mkdir(parents=True)
    write_executable(bin_dir / "voxen", '#!/bin/sh\nexec /usr/lib/voxen/Voxen "$@"\n')
    desktop = usr / "share" / "applications" / "voxen.desktop"
    desktop.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "installer" / "linux" / "voxen.desktop", desktop)
    icon = usr / "share" / "icons" / "hicolor" / "256x256" / "apps" / "voxen.png"
    icon.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "assets" / "voxen-system.png", icon)
    doc = usr / "share" / "doc" / "voxen" / "copyright"
    doc.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", doc)
    subprocess.run(["desktop-file-validate", str(desktop)], check=True)
    control = appdir / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        f"Package: voxen\nVersion: {version}\nSection: utils\nPriority: optional\nArchitecture: amd64\n"
        "Maintainer: Voxen contributors\n"
        "Depends: libc6 (>= 2.35), libportaudio2, xclip, libx11-6, libxtst6, libxext6, libxrender1, libxi6, libxkbcommon0\n"
        "Recommends: libglib2.0-bin, xdg-desktop-portal\n"
        "Description: Local-first voice dictation for X11 desktops\n",
        encoding="utf-8",
    )
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(appdir), str(DIST / f"voxen_{version}_amd64.deb")], check=True)
    shutil.rmtree(control)
    write_executable(bin_dir / "voxen", '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$HERE/../lib/voxen/Voxen" "$@"\n')
    shutil.copyfile(desktop, appdir / "voxen.desktop")
    shutil.copyfile(icon, appdir / "voxen.png")
    write_executable(appdir / "AppRun", '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexec "$HERE/usr/bin/voxen" "$@"\n')
    target = DIST / f"Voxen-{version}-x86_64.AppImage"
    subprocess.run([tool, str(appdir), str(target)], check=True,
                   env=dict(os.environ, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1"))
    target.chmod(0o755)


if __name__ == "__main__":
    main()
