import sys

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
