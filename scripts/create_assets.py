"""Generate all raster application icons from the transparent SVG monogram."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter
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


def recolor(mark: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    result = Image.new("RGBA", mark.size, (*color, 0))
    result.putalpha(mark.getchannel("A"))
    return result


def system_mark(mark: Image.Image) -> Image.Image:
    """A fine white keyline keeps a transparent dark mark legible on any tray."""
    alpha = mark.getchannel("A")
    radius = max(1, round(mark.width * 0.032))
    backing = Image.new("RGBA", mark.size, (255, 255, 255, 0))
    backing.putalpha(alpha.filter(ImageFilter.MaxFilter(radius * 2 + 1)))
    backing.alpha_composite(mark)
    return backing


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    mark = render_mark()
    mark.save(ASSETS / "voxen-mark.png", optimize=True)
    recolor(mark, (241, 241, 243)).save(ASSETS / "voxen-mark-dark.png", optimize=True)
    system = system_mark(mark)
    system.save(ASSETS / "voxen-system.png", optimize=True)
    sizes = [16, 32, 48, 64, 128, 256]
    # Render each size individually for crisp edges at tray resolution.
    icons = [system_mark(render_mark(size)) for size in sizes]
    system.save(ASSETS / "voxen.ico", sizes=[(n, n) for n in sizes], append_images=icons)
    system_mark(render_mark(1024)).save(ASSETS / "voxen.icns", format="ICNS")
    print("Created transparent Voxen PNG, ICO and ICNS assets")


if __name__ == "__main__":
    main()
