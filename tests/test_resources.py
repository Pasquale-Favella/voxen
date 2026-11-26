import sys

from PIL import Image

from voxen.infrastructure import resources


def test_asset_path_finds_the_repository_assets_directory() -> None:
    path = resources.asset_path("voxen-mark.png")
    assert path.name == "voxen-mark.png"
    assert path.parent.name == "assets"
    assert path.exists()


def test_asset_path_uses_meipass_when_frozen(monkeypatch, tmp_path) -> None:
    (tmp_path / "assets").mkdir()
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    path = resources.asset_path("voxen-mark.png")

    assert path == tmp_path / "assets" / "voxen-mark.png"


def test_asset_path_raises_when_nothing_is_found(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(resources, "_MAX_SEARCH_DEPTH", 0)

    try:
        resources.asset_path("voxen-mark.png")
    except resources.AssetNotFoundError:
        return
    raise AssertionError("expected AssetNotFoundError")



def test_brand_assets_are_transparent_and_theme_adaptive() -> None:
    with Image.open(resources.asset_path("voxen-mark.png")) as light, Image.open(resources.asset_path("voxen-mark-dark.png")) as dark:
        assert light.mode == dark.mode == "RGBA"
        assert light.size == dark.size == (256, 256)
        assert light.getchannel("A").tobytes() == dark.getchannel("A").tobytes()
        for mark in (light, dark):
            assert mark.getpixel((0, 0))[3] == 0
            assert mark.getchannel("A").getextrema() == (0, 255)
        assert light.getpixel((0, 0))[:3] != dark.getpixel((0, 0))[:3] or light.tobytes() != dark.tobytes()
    with Image.open(resources.asset_path("voxen-system.png")) as system:
        assert system.mode == "RGBA"
        assert system.getpixel((0, 0))[3] == 0
    with Image.open(resources.asset_path("voxen.ico")) as icon:
        assert (16, 16) in icon.ico.sizes()
        assert (256, 256) in icon.ico.sizes()



def test_readme_vector_marks_share_the_same_continuous_silhouette() -> None:
    from xml.etree import ElementTree as ET

    namespace = {"svg": "http://www.w3.org/2000/svg"}
    light = ET.parse(resources.asset_path("voxen-mark.svg")).getroot()
    dark = ET.parse(resources.asset_path("voxen-mark-dark.svg")).getroot()
    light_paths = light.findall(".//svg:path", namespace)
    dark_paths = dark.findall(".//svg:path", namespace)
    assert len(light_paths) == len(dark_paths) == 1
    assert light_paths[0].attrib["d"] == dark_paths[0].attrib["d"]
    assert light_paths[0].attrib["fill"] == "#18181b"
    assert dark_paths[0].attrib["fill"] == "#f1f1f3"
    assert not light.findall(".//svg:rect", namespace)
    assert not dark.findall(".//svg:rect", namespace)
