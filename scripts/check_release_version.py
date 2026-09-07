from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path


def read_versions(root: Path) -> dict[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    init_text = (root / "src" / "voxen" / "__init__.py").read_text(encoding="utf-8")
    installer_text = (root / "installer" / "Voxen.iss").read_text(encoding="utf-8")
    init_match = re.search(r"^__version__\s*=\s*\"([^\"]+)\"", init_text, re.MULTILINE)
    installer_match = re.search(r'^#define MyAppVersion "([^"]+)"', installer_text, re.MULTILINE)
    if init_match is None or installer_match is None:
        raise ValueError("Impossibile leggere una versione del progetto.")
    return {
        "tag": "",
        "project": project["project"]["version"],
        "package": init_match.group(1),
        "installer": installer_match.group(1),
    }


def validate_release_version(root: Path, tag: str) -> str:
    expected = tag.removeprefix("v")
    versions = read_versions(root)
    versions["tag"] = expected
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise ValueError(f"Versioni release incoerenti: {details}")
    return expected


def main() -> int:
    tag = os.environ.get("RELEASE_TAG") or os.environ.get("GITHUB_REF_NAME")
    if not tag:
        raise SystemExit("RELEASE_TAG o GITHUB_REF_NAME è richiesto.")
    version = validate_release_version(Path(__file__).resolve().parents[1], tag)
    print(f"Release versions consistent: {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())