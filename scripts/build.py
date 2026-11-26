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
    if sys.platform not in {"win32", "darwin", "linux"}:
        raise SystemExit("Voxen packaging supports Windows, macOS and Linux only.")

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
    ]
    # The default engine must be present in every installer; fail before packaging
    # if the runtime is missing, and collect its metadata and native libraries.
    run([sys.executable, "-c", "from onnx_asr.loader import Manager; import onnxruntime"])
    for package in ("onnx_asr", "onnxruntime"):
        command += ["--collect-all", package]
    command += ["--add-data", f"{ROOT / 'LICENSE'}{data_separator}."]
    for asset in ("voxen-mark.png", "voxen-mark-dark.png", "voxen-system.png"):
        command += ["--add-data", f"{ROOT / 'assets' / asset}{data_separator}assets"]
    if sys.platform == "win32":
        command += [
            "--icon",
            str(ROOT / "assets" / "voxen.ico"),
            "--hidden-import",
            "pystray._win32",
            "--hidden-import",
            "pynput.keyboard._win32",
        ]
    elif sys.platform == "darwin":
        command += [
            "--icon",
            str(ROOT / "assets" / "voxen.icns"),
            "--hidden-import",
            "pystray._darwin",
            "--hidden-import",
            "pynput.keyboard._darwin",
        ]
    else:
        command += ["--hidden-import", "pynput.keyboard._xorg", "--hidden-import", "pynput.mouse._xorg",
                    "--hidden-import", "pyautogui._pyautogui_x11"]
    command.append(str(ROOT / "src" / "voxen" / "__main__.py"))
    run(command)

    if sys.platform == "win32":
        installer = shutil.which("iscc") or shutil.which("ISCC.exe")
        if installer:
            run([installer, str(ROOT / "installer" / "Voxen.iss")])
        else:
            archive = shutil.make_archive(str(DIST / "Voxen-windows"), "zip", DIST / "Voxen")
            print(f"Inno Setup not found; created archive: {archive}")
    elif sys.platform == "darwin":
        # PyInstaller --windowed on macOS emits dist/Voxen.app; fail fast
        # with a clear message instead of a cryptic hdiutil error.
        app_bundle = DIST / "Voxen.app"
        if not app_bundle.exists():
            raise SystemExit(f"Expected macOS bundle not found: {app_bundle}")
        dmg = DIST / "Voxen-macos.dmg"
        run(["hdiutil", "create", "-volname", "Voxen", "-srcfolder", str(app_bundle), "-ov", str(dmg)])
        print(f"Created disk image: {dmg}")
    else:
        run([sys.executable, str(ROOT / "scripts" / "package_linux.py")])


if __name__ == "__main__":
    main()
