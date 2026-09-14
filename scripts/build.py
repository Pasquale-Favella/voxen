from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    if sys.platform not in {"win32", "darwin"}:
        raise SystemExit("Voxen packaging supports Windows and macOS only.")

    pyinstaller = [sys.executable, "-m", "PyInstaller"]
    run([sys.executable, str(ROOT / "scripts" / "create_assets.py")])
    data_separator = ";" if sys.platform == "win32" else ":"
    command = pyinstaller + [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        "--name",
        "Voxen",
        "--paths",
        str(ROOT / "src"),
        "--collect-all",
        "faster_whisper",
        "--collect-all",
        "ctranslate2",
        "--collect-all",
        "av",
        "--add-data",
        f"{ROOT / 'assets' / 'voxen-mark.png'}{data_separator}assets",
    ]
    if sys.platform == "win32":
        command += [
            "--icon",
            str(ROOT / "assets" / "voxen.ico"),
            "--hidden-import",
            "pystray._win32",
            "--hidden-import",
            "pynput.keyboard._win32",
        ]
    else:
        command += [
            "--hidden-import",
            "pystray._darwin",
            "--hidden-import",
            "pynput.keyboard._darwin",
        ]
    command.append(str(ROOT / "src" / "voxen" / "__main__.py"))
    run(command)

    if sys.platform == "win32":
        installer = shutil.which("iscc") or shutil.which("ISCC.exe")
        if installer:
            run([installer, str(ROOT / "installer" / "Voxen.iss")])
        else:
            archive = shutil.make_archive(str(DIST / "Voxen-windows"), "zip", DIST / "Voxen")
            print(f"Inno Setup not found; created archive: {archive}")
    else:
        # PyInstaller --windowed on macOS emits dist/Voxen.app; fail fast
        # with a clear message instead of a cryptic hdiutil error.
        app_bundle = DIST / "Voxen.app"
        if not app_bundle.exists():
            raise SystemExit(f"Expected macOS bundle not found: {app_bundle}")
        dmg = DIST / "Voxen-macos.dmg"
        run(["hdiutil", "create", "-volname", "Voxen", "-srcfolder", str(app_bundle), "-ov", str(dmg)])
        print(f"Created disk image: {dmg}")


if __name__ == "__main__":
    main()
