"""Wraps bump-my-version to bump every project sharing a version group in one commit+tag. Writes
a temporary per-group `.bumpversion.toml` at call time instead of a static one — confirmed
hands-on that bump-my-version's config-free CLI mode can't express a different search/replace
template per file, and a group's file set (which projects/charts belong to it) isn't fixed ahead
of time, only resolved from projects.py/repo-tasks.toml at call time."""

import tempfile
from pathlib import Path

from invoke import task

from .projects import discover_helm_charts, discover_python_projects


def _resolve_project(c, group):
    """The python project whose `[project].version` is the group's version. Absence is an error
    here, not a no-op like `dist.py`/`docker.py`/`helm.py`: nothing else can supply a version, so a
    bump has nothing to write and a `current_version` query has nothing to answer — say so, rather
    than an IndexError out of `[0]`."""
    python_projects = discover_python_projects(c)
    if group is not None:
        python_projects = [p for p in python_projects if p.name == group]
        if not python_projects:
            raise ValueError(f"no project found for group {group!r}")
    if not python_projects:
        raise ValueError("no python project found (no pyproject.toml [project] table and no workspace members)")
    return python_projects[0]


def current_version(c, group=None):
    """The current version of one group's project, resolved via projects.py."""
    return _resolve_project(c, group).version


def next_version(current, part):
    """The version `bump` would produce for `part`, computed without writing or committing
    anything. Safe to hand-roll here (rather than shell out to bump-my-version to compute it):
    our generated config never customizes parse/serialize, so every version this repo ever bumps
    is plain major.minor.patch, bump-my-version's own default scheme. gitflow.py uses this to name
    a release/hotfix branch *before* the bump commit exists — nvie's branch-then-bump order — the
    actual file-writing/committing still stays fully owned by bump-my-version via `bump` below."""
    major_s, minor_s, patch_s = current.split(".")
    major, minor, patch = int(major_s), int(minor_s), int(patch_s)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown version part {part!r}")


def _bumpversion_config(project, charts, tag) -> str:
    pyproject_path = project.path / "pyproject.toml"
    tag_config = 'tag = true\ntag_name = "v{new_version}"' if tag else "tag = false"
    config = f"""\
[tool.bumpversion]
current_version = "{project.version}"
commit = true
{tag_config}

[[tool.bumpversion.files]]
filename = "{pyproject_path}"
search = 'version = "{{current_version}}"'
replace = 'version = "{{new_version}}"'
"""
    # The search patterns assume `helm create`'s own scaffold quoting: `version:` unquoted,
    # `appVersion:` quoted. The quoted appVersion form also keeps the bare `version: X` search
    # from matching inside the appVersion line (`version: X` is a substring of an unquoted
    # `appVersion: X`). bump-my-version fails loudly when a search string is absent, so a chart
    # straying from that quoting breaks the bump instead of half-applying it.
    for chart in charts:
        chart_yaml = chart.path / "Chart.yaml"
        config += f"""
[[tool.bumpversion.files]]
filename = "{chart_yaml}"
search = "version: {{current_version}}"
replace = "version: {{new_version}}"

[[tool.bumpversion.files]]
filename = "{chart_yaml}"
search = 'appVersion: "{{current_version}}"'
replace = 'appVersion: "{{new_version}}"'
"""
    return config


def _bump(c, part, group=None, tag=True):
    project = _resolve_project(c, group)
    charts = [chart for chart in discover_helm_charts(c) if chart.group == project.name]
    config = _bumpversion_config(project, charts, tag)
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
        _ = f.write(config)
        config_path = Path(f.name)

    try:
        c.run(f"bump-my-version bump {part} --config-file {config_path}", echo=True)
    finally:
        config_path.unlink()

    return discover_python_projects(c)[0].version


@task
def bump(c, part, group=None, tag=True):
    """Bump one version group (major/minor/patch): writes the new version into every file that
    group's projects live in and commits. Tags `vX.Y.Z` unless `tag=False` — gitflow.py's
    release_start/hotfix_start pass tag=False since the tag belongs on main at finish time, not on
    develop at bump time. Returns the new version string."""
    return _bump(c, part, group=group, tag=tag)
