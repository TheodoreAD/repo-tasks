"""Wraps bump-my-version to bump every project sharing a version group in one commit+tag. Writes
a temporary per-group `.bumpversion.toml` at call time instead of a static one — confirmed
hands-on that bump-my-version's config-free CLI mode can't express a different search/replace
template per file, and a group's file set (which projects/charts belong to it) isn't fixed ahead
of time, only resolved from projects.py/repo-tasks.toml at call time."""

import tempfile
from pathlib import Path

from invoke import task

from .projects import discover_python_projects


def _bumpversion_config(project, tag) -> str:
    pyproject_path = project.path / "pyproject.toml"
    tag_config = 'tag = true\ntag_name = "v{new_version}"' if tag else "tag = false"
    return f"""\
[tool.bumpversion]
current_version = "{project.version}"
commit = true
{tag_config}

[[tool.bumpversion.files]]
filename = "{pyproject_path}"
search = 'version = "{{current_version}}"'
replace = 'version = "{{new_version}}"'
"""


def _bump(c, part, group=None, tag=True):
    python_projects = discover_python_projects(c)
    if group is not None:
        python_projects = [p for p in python_projects if p.name == group]
        if not python_projects:
            raise ValueError(f"no project found for group {group!r}")

    config = _bumpversion_config(python_projects[0], tag)
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
