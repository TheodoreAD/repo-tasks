"""Fixtures shared by every tier. Deliberately thin — anything that only one tier needs belongs in
that tier's own conftest, so a unit test can never reach an integration fixture by accident. That
separation is most of the reason the two directories exist at all."""

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """This repo's own root, resolved from this file rather than from the working directory —
    several tests chdir into tmp_path and still need to reach real committed files. Session-scoped
    so module-scoped fixtures can depend on it; pytest forbids the other direction."""
    return _REPO_ROOT
