"""Fixtures shared by every tier. Deliberately thin — anything that only one tier needs belongs in
that tier's own conftest, so a unit test can never reach an integration fixture by accident. That
separation is most of the reason the two directories exist at all."""

import tomllib
from pathlib import Path
from typing import cast

import pytest

_REPO_ROOT = Path(__file__).parent.parent
_SAMPLE_SERVICE = "sample-service"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """This repo's own root, resolved from this file rather than from the working directory —
    several tests chdir into tmp_path and still need to reach real committed files. Session-scoped
    so module-scoped fixtures can depend on it; pytest forbids the other direction."""
    return _REPO_ROOT


@pytest.fixture(scope="session")
def sample_chart_dir(repo_root: Path) -> Path:
    """The dogfood chart's directory, read out of repo-tasks.toml rather than written as a literal.

    Two tiers reach for this, and a literal path in either is a trap: moving the fixture tree
    (examples/ -> tests/fixtures/, as happened) leaves the literal pointing at nothing, and the
    failure surfaces as a confusing mid-test read error rather than at collection. Resolving from
    the same config the tasks themselves read means the tests cannot disagree with them."""
    with (repo_root / "repo-tasks.toml").open("rb") as f:
        data = cast(dict[str, list[dict[str, str]]], tomllib.load(f))
    entry = next(e for e in data["helm"] if e["name"] == _SAMPLE_SERVICE)
    return repo_root / entry["path"]
