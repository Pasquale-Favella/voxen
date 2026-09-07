from pathlib import Path

import pytest

from scripts.check_release_version import validate_release_version

ROOT = Path(__file__).parents[1]


def test_release_version_matches_project_metadata() -> None:
    assert validate_release_version(ROOT, "v0.1.2") == "0.1.2"


def test_release_version_rejects_mismatched_tag() -> None:
    with pytest.raises(ValueError, match="incoerenti"):
        validate_release_version(ROOT, "v9.9.9")