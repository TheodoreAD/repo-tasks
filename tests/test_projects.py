"""Tests for repo_tasks.projects: Phase 1's single-implicit-project fallback, run against this
repo's own pyproject.toml (mirrors test_quality.py's existing MockContext style, though
discover_python_projects doesn't touch c.run yet)."""

from pathlib import Path

from invoke import MockContext

from repo_tasks import projects


def test_discover_python_projects_returns_repo_root_as_sole_project():
    c = MockContext(run=True)
    result = projects.discover_python_projects(c)
    assert result == [projects.PythonProject(name="repo-tasks", path=Path(), version="0.1.0")]
