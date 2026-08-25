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

from invoke.context import Context

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


def _load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as f:
        return cast(dict[str, object], tomllib.load(f))


def _project_at(path: Path, data: dict[str, object]) -> PythonProject | None:
    """One `[project]` table as a PythonProject, or None for a table-less pyproject.toml — a
    workspace root that only groups members (uv's "virtual" root) legitimately has none."""
    project = cast(dict[str, str] | None, data.get("project"))
    if project is None:
        return None
    return PythonProject(name=project["name"], path=path, version=project["version"])


def _workspace_member_dirs(data: dict[str, object]) -> list[Path]:
    """Every directory matched by `[tool.uv.workspace].members` and not by its `exclude` — uv's
    own two globs, both relative to the workspace root. Sorted so the resolved project order is
    stable across filesystems, which matters because callers index `[0]`."""
    tool = cast(dict[str, object], data.get("tool", {}))
    uv = cast(dict[str, object], tool.get("uv", {}))
    workspace = cast(dict[str, list[str]] | None, uv.get("workspace"))
    if workspace is None:
        return []

    root = Path()
    included = {d for pattern in workspace.get("members", []) for d in root.glob(pattern) if d.is_dir()}
    excluded = {d for pattern in workspace.get("exclude", []) for d in root.glob(pattern)}
    return sorted(included - excluded)


def discover_python_projects(c: Context) -> list[PythonProject]:
    """Resolve every python project in the consumer repo, the root's own first. `c` is unused —
    kept in the signature for symmetry with the other two discover functions.

    No `[tool.uv.workspace]` in the root pyproject.toml means the repo root's own `[project]`
    table is the one implicit project (Phase 1, still the common case and still zero-config).
    With one, each `members` glob's own pyproject.toml resolves into its own PythonProject too
    — `uv`'s workspace table is the source of truth, never a parallel manifest of our own.

    Root-first ordering is load-bearing: `dist.py` and `version.py` treat `[0]` as "the repo's
    own project" when no `--project`/`--group` narrows it down, so adding a workspace member must
    never change what a no-flag invocation acts on.

    No `pyproject.toml` at all is an empty list, not an error — a Dockerfile-only or
    quality-gates-only repo is a normal state, and each caller decides what absence means for it
    (`dist.*` no-op, `version.*` raise, `discover_docker_images` falls back to the directory name).
    """
    root_pyproject = Path("pyproject.toml")
    if not root_pyproject.exists():
        return []
    root_data = _load_toml(root_pyproject)
    root = _project_at(Path(), root_data)
    projects = [root] if root is not None else []

    for member_dir in _workspace_member_dirs(root_data):
        member_pyproject = member_dir / "pyproject.toml"
        if not member_pyproject.exists():
            continue
        member = _project_at(member_dir, _load_toml(member_pyproject))
        if member is not None:
            projects.append(member)
    return projects


def _load_repo_tasks_toml() -> dict[str, object]:
    if not _REPO_TASKS_TOML.exists():
        return {}
    return _load_toml(_REPO_TASKS_TOML)


def discover_docker_images(c: Context) -> list[DockerImage]:
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
    python_projects = discover_python_projects(c)
    name = python_projects[0].name if python_projects else Path.cwd().name
    return [DockerImage(name=name, path=Path(), dockerfile=dockerfile, image=name, group=name)]


def discover_helm_charts(c: Context) -> list[HelmChart]:
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
