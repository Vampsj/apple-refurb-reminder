from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_public_package_metadata_is_multi_region() -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert metadata["version"].startswith("1.0.0")
    assert "regional Apple refurbished inventory" in metadata["description"]
    assert metadata["license"] == "MIT"


def test_ci_covers_supported_macos_and_experimental_linux() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "macos-14" in workflow
    assert "ubuntu-latest" in workflow
    assert '"3.13"' in workflow
    assert "uv build" in workflow
