"""Project discovery. Python projects reuse `uv`'s own workspace mechanism as the source of truth
instead of inventing a parallel manifest; docker images and Helm charts aren't modeled by `uv` at
all, so they resolve from `repo-tasks.toml`'s `[[docker]]`/`[[helm]]` entries instead, with a
zero-config Dockerfile-at-root fallback for the common single-image case. Every later task module
(docker.py, dist.py, helm.py, version.py) calls into here instead of hardcoding "the repo
root"."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_REPO_TASKS_TOML = Path("repo-tasks.toml")


@dataclass(frozen=True)
class PythonProject:
    name: str
    path: Path
    version: str


@dataclass(frozen=True)
class DockerImage:
    name: str
    path: Path
    dockerfile: Path
    image: str
    group: str


@dataclass(frozen=True)
class HelmChart:
    name: str
    path: Path
    registry: str | None
    group: str


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


def _load_repo_tasks_toml() -> dict[str, object]:
    if not _REPO_TASKS_TOML.exists():
        return {}
    with _REPO_TASKS_TOML.open("rb") as f:
        return cast(dict[str, object], tomllib.load(f))


def discover_docker_images(c) -> list[DockerImage]:
    """Resolve every docker image this repo builds.

    Explicit config (`repo-tasks.toml`'s `[[docker]]` entries) always wins when present. With no
    config at all — the common single-image case — a `Dockerfile` at the repo root is treated as
    one implicit image, the same zero-config ergonomics as `discover_python_projects`'s Phase 1
    fallback: named after the repo's python project (so it shares that project's version group for
    free), or the repo directory's own name if there isn't one. `image` defaults to that same name
    — a local-only placeholder good enough for `docker build`/local testing; a real
    registry-qualified name needs an explicit `[[docker]]` entry.
    """
    data = _load_repo_tasks_toml()
    entries = cast(list[dict[str, str]], data.get("docker", []))
    if entries:
        return [
            DockerImage(
                name=entry["name"],
                path=Path(entry["path"]),
                dockerfile=Path(entry["dockerfile"]),
                image=entry["image"],
                group=entry.get("group", entry["name"]),
            )
            for entry in entries
        ]

    dockerfile = Path("Dockerfile")
    if not dockerfile.exists():
        return []
    try:
        python_projects = discover_python_projects(c)
    except FileNotFoundError:
        python_projects = []
    name = python_projects[0].name if python_projects else Path.cwd().name
    return [DockerImage(name=name, path=Path(), dockerfile=dockerfile, image=name, group=name)]


def discover_helm_charts(c) -> list[HelmChart]:
    """Resolve every helm chart this repo ships — `repo-tasks.toml`'s `[[helm]]` entries only,
    an empty list otherwise. No zero-config fallback, unlike `discover_docker_images`: a chart
    has no single canonical root location the way a `Dockerfile` does, and a pushable chart needs
    a registry only explicit config can supply. `registry` is optional in the entry (lint/package
    don't need one); `helm.push` is the task that insists on it."""
    data = _load_repo_tasks_toml()
    entries = cast(list[dict[str, str]], data.get("helm", []))
    return [
        HelmChart(
            name=entry["name"],
            path=Path(entry["path"]),
            registry=entry.get("registry"),
            group=entry.get("group", entry["name"]),
        )
        for entry in entries
    ]
