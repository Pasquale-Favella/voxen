"""Locates bundled assets (icons, images) across dev and frozen (PyInstaller) runs.

Both the dashboard (brand image) and the tray (icon) used to each hardcode
``Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))``. The
``parents[2]`` guess only works because of the current ``src/voxen/...``
depth; it silently breaks the moment a module moves a directory deeper (as
happened when this file itself was placed under ``infrastructure/``).
Resolving it once, by searching upward for the ``assets`` directory instead
of hardcoding its depth, removes both the duplication and that fragility.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ASSETS_DIRNAME = "assets"
_MAX_SEARCH_DEPTH = 6


class AssetNotFoundError(RuntimeError):
    pass


def _frozen_root() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def _find_assets_root() -> Path:
    frozen = _frozen_root()
    if frozen is not None:
        return frozen
    candidate = Path(__file__).resolve()
    for _ in range(_MAX_SEARCH_DEPTH):
        candidate = candidate.parent
        if (candidate / _ASSETS_DIRNAME).is_dir():
            return candidate
    raise AssetNotFoundError(
        f"Impossibile trovare la cartella '{_ASSETS_DIRNAME}' a partire da {Path(__file__).resolve()}."
    )


def asset_path(*parts: str) -> Path:
    """Return the path to a file under the bundled ``assets`` directory."""
    path = _find_assets_root() / _ASSETS_DIRNAME
    for part in parts:
        path = path / part
    return path
