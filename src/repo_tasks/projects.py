"""Project discovery. Python projects reuse `uv`'s own workspace mechanism as the source of truth
instead of inventing a parallel manifest; docker images and Helm charts aren't modeled by `uv` at
all, so they resolve from `repo-tasks.toml`'s `[[docker]]`/`[[helm]]` entries instead, with a
zero-config Dockerfile-at-root fallback for the common single-image case. Every later task module
(docker.py, dist.py, helm.py, version.py) calls into here instead of hardcoding "the repo
root"."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from invoke import Context

_REPO_TASKS_TOML = Path("repo-tasks.toml")

# The repo root, as every task here already assumes: cwd. A module constant rather than a `Path()`
# call in a parameter default, which `reportCallInDefaultInitializer` rejects.
_CWD = Path()


def tracked_files(c: Context, *patterns: str) -> list[str]:
    """Files matching the git pathspecs — tracked, or untracked but not ignored, so a file written a
    moment ago is seen before it is ever `git add`ed and `.gitignore` is honoured without any tool
    needing its own exclude list.

    An empty list on any git failure (not a repo at all), which every caller treats as "nothing to
    do" — that is what lets each file-gated step no-op cleanly instead of erroring.

    Lives here rather than in quality.py, where it started, because docs.py needs the same listing
    and quality.py imports docs.py for the gate's pre-chain: the other direction would be an import
    cycle. Discovery is this module's job anyway."""
    specs = " ".join(f"'{p}'" for p in patterns)
    result = c.run(f"git ls-files --cached --others --exclude-standard -- {specs}", hide=True, warn=True)
    return result.stdout.split() if result.ok else []


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


# The branch names every git-flow-shaped task assumed as literals until 2026-09-06. `main`/`develop`
# stay the defaults — they are this family's convention and no consumer following it has to write
# anything — but they are now one answer read from one place instead of ~25 string literals across
# four modules, so a repo on a different trunk has something to set.
_DEFAULT_TRUNK = "main"
_DEFAULT_DEVELOP = "develop"


def _branch_setting(key: str, default: str, root: Path) -> str:
    config = root / _REPO_TASKS_TOML
    if not config.is_file():
        return default
    branches = _load_toml(config).get("branches")
    if not isinstance(branches, dict):
        return default
    value = cast(dict[str, object], branches).get(key)
    return value if isinstance(value, str) and value else default


def trunk_branch(root: Path = _CWD) -> str:
    """The branch releases land on and hotfixes come off — `repo-tasks.toml`'s `[branches] trunk`,
    else `main`.

    Read rather than hardcoded because a repo on `master` could not use `gitflow` at all: its tasks
    had `main` written into `_start`, `_pr_finish`, `_finalize` and the merged-PR check with no flag
    to override, so `hotfix_start` branched off a branch that does not exist there. `ci.status`,
    `trunkflow.cut` and `release.push_tag` each took a `--branch` defaulting to `main`, which worked
    but had to be typed on every single call — recorded as a per-consumer ergonomic on
    `power-user-linux-setup`, which is on `master`. Both are the same missing setting."""
    return _branch_setting("trunk", _DEFAULT_TRUNK, root)


def develop_branch(root: Path = _CWD) -> str:
    """The integration branch features come off and releases merge back into — `repo-tasks.toml`'s
    `[branches] develop`, else `develop`. Only `gitflow` uses it; `trunkflow` has no such branch by
    definition."""
    return _branch_setting("develop", _DEFAULT_DEVELOP, root)


def python_floor(root: Path = _CWD) -> str | None:
    """The `major.minor` a project declares as its lowest supported Python, or None when it declares
    no `requires-python` at all.

    One reader, because three things now target the same declaration and must not disagree about
    what it says: the `pythonVersion` `configs.pull` derives into a consumer's pyrightconfig.json,
    the interpreter `venv.recreate` builds against, and ruff's own inference (which reads
    `requires-python` directly and needs nothing from here). A project's declared floor is a project
    fact, so it lives with the rest of discovery rather than in whichever module needed it first."""
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    project = cast(dict[str, object], _load_toml(pyproject).get("project", {}))
    spec = project.get("requires-python")
    if not isinstance(spec, str):
        return None
    # `>=3.11`, `>=3.11.0`, `~=3.11`, `>=3.11,<4` — the floor is the first lower bound whichever
    # operator states it. An upper bound alone (`<4`) declares no floor and is correctly no match.
    match = re.search(r"(?:>=|~=|==)\s*(\d+\.\d+)", spec)
    return match.group(1) if match else None


def _project_at(path: Path, data: dict[str, object]) -> PythonProject | None:
    """One `[project]` table as a PythonProject, or None for a table-less pyproject.toml — a
    workspace root that only groups members (uv's "virtual" root) legitimately has none.

    A table that is present but missing `name` or `version` raises, naming the file and the key. It
    raised before too — with a bare `KeyError: 'version'` out of a dict subscript, which says
    nothing about which of a workspace's pyproject.toml files it came from. The realistic cause is
    `dynamic = ["version"]` (hatch-vcs, setuptools-scm): this package's whole version model is a
    static field that `version.bump` rewrites in place, so a project deriving its version from git
    is not something discovery can answer for, and saying so beats a KeyError."""
    project = cast(dict[str, str] | None, data.get("project"))
    if project is None:
        return None
    missing = [key for key in ("name", "version") if key not in project]
    if missing:
        raise ValueError(
            f"{path / 'pyproject.toml'}: [project] declares no {' or '.join(missing)}"
            + (
                ' — a version derived at build time (dynamic = ["version"]) is not supported: '
                "repo-tasks reads and rewrites a static field"
                if "version" in missing
                else ""
            )
        )
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


def _field(entry: dict[str, str], key: str, table: str) -> str:
    """One required key of a `repo-tasks.toml` entry, or a message naming the file, the table and
    the key. `repo-tasks.toml` is hand-authored, so a missing key is an ordinary typo — and a bare
    `KeyError: 'dockerfile'` names neither the file it came from nor which of several entries."""
    value = entry.get(key)
    if value is None:
        raise ValueError(f"{_REPO_TASKS_TOML}: a [[{table}]] entry declares no {key} ({entry!r})")
    return value


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
                name=_field(entry, "name", "docker"),
                path=Path(_field(entry, "path", "docker")),
                dockerfile=Path(_field(entry, "dockerfile", "docker")),
                image=_field(entry, "image", "docker"),
                group=entry.get("group", _field(entry, "name", "docker")),
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
            name=_field(entry, "name", "helm"),
            path=Path(_field(entry, "path", "helm")),
            registry=entry.get("registry"),
            group=entry.get("group", _field(entry, "name", "helm")),
        )
        for entry in entries
    ]
