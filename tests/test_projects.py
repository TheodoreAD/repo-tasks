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


def test_discover_docker_images_empty_with_no_config_and_no_dockerfile(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = MockContext(run=True)
    assert projects.discover_docker_images(c) == []


def test_discover_docker_images_zero_config_default_uses_python_project_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "1.0.0"\n')
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    c = MockContext(run=True)
    assert projects.discover_docker_images(c) == [
        projects.DockerImage(
            name="sample-service",
            path=Path(),
            dockerfile=Path("Dockerfile"),
            image="sample-service",
            group="sample-service",
        )
    ]


def test_discover_docker_images_zero_config_default_falls_back_to_dirname_without_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM scratch\n")
    c = MockContext(run=True)
    result = projects.discover_docker_images(c)
    assert result == [
        projects.DockerImage(
            name=tmp_path.name, path=Path(), dockerfile=Path("Dockerfile"), image=tmp_path.name, group=tmp_path.name
        )
    ]


def test_discover_docker_images_reads_explicit_repo_tasks_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repo-tasks.toml").write_text(
        "[[docker]]\n"
        'name = "sample-service"\n'
        'path = "examples/sample-service"\n'
        'dockerfile = "examples/sample-service/Dockerfile"\n'
        'image = "ghcr.io/org/sample-service"\n'
        'group = "sample-service"\n'
    )
    c = MockContext(run=True)
    assert projects.discover_docker_images(c) == [
        projects.DockerImage(
            name="sample-service",
            path=Path("examples/sample-service"),
            dockerfile=Path("examples/sample-service/Dockerfile"),
            image="ghcr.io/org/sample-service",
            group="sample-service",
        )
    ]


def test_discover_docker_images_explicit_entry_group_defaults_to_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repo-tasks.toml").write_text(
        '[[docker]]\nname = "solo"\npath = "."\ndockerfile = "Dockerfile"\nimage = "ghcr.io/org/solo"\n'
    )
    c = MockContext(run=True)
    result = projects.discover_docker_images(c)
    assert result[0].group == "solo"
