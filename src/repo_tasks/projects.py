"""Python project discovery, reusing `uv`'s own workspace mechanism as the source of truth
instead of inventing a parallel manifest. Every later task module (docker.py, python_pkg.py,
helm.py, version.py) calls discover_python_projects instead of hardcoding "the repo root"."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class PythonProject:
    name: str
    path: Path
    version: str


def discover_python_projects(c) -> list[PythonProject]:
    """Resolve every python project in the consumer repo. `c` is unused in Phase 1 — kept in the
    signature since Phase 2's workspace-glob resolution will need it.

    Phase 1: no `[tool.uv.workspace]` in the root pyproject.toml means the repo root's own
    `[project]` table is the one implicit project. Phase 2 will additionally resolve each
    `[tool.uv.workspace].members` glob's own pyproject.toml into its own PythonProject.
    """
    pyproject_path = Path("pyproject.toml")
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)

    project = cast(dict[str, str], data["project"])
    return [PythonProject(name=project["name"], path=Path(), version=project["version"])]
