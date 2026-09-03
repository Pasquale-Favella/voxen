from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from resvg_py import svg_to_bytes

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def render_mark(size: int = 256) -> Image.Image:
    png = svg_to_bytes(
        svg_path=str(ASSETS / "voxen-mark.svg"),
        width=size,
        height=size,
        shape_rendering="geometric_precision",
    )
    return Image.open(BytesIO(png)).convert("RGBA")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    mark = render_mark()
    mark.save(ASSETS / "voxen-mark.png", optimize=True)
    mark.save(ASSETS / "voxen.ico", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print(f"Created {ASSETS / 'voxen-mark.png'} and {ASSETS / 'voxen.ico'}")


if __name__ == "__main__":
    main()
