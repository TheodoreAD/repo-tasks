"""Tests for repo_tasks.projects: the single-implicit-project fallback run against this repo's own
pyproject.toml, plus workspace-member resolution against throwaway trees built in tmp_path (mirrors
test_quality.py's existing MockContext style, though discover_python_projects doesn't touch c.run).

The workspace cases deliberately build their own minimal tree rather than pointing at this repo's
real examples/ — discovery logic gets a fast, minimal case it fully controls (an excluded member, a
member dir with no pyproject.toml, a table-less root), independent of whatever the dogfood sample
happens to look like."""

from pathlib import Path

from invoke import MockContext

from repo_tasks import projects

_ROOT_PYPROJECT = '[project]\nname = "root-pkg"\nversion = "1.0.0"\n'


def _write_member(root: Path, relative: str, name: str, version: str) -> None:
    member = root / relative
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "{version}"\n')


def _write_workspace_root(root: Path, members: str, exclude: str = "", project: str = _ROOT_PYPROJECT) -> None:
    exclude_line = f"exclude = {exclude}\n" if exclude else ""
    (root / "pyproject.toml").write_text(f"{project}\n[tool.uv.workspace]\nmembers = {members}\n{exclude_line}")


def test_discover_python_projects_returns_repo_root_first():
    c = MockContext(run=True)
    result = projects.discover_python_projects(c)
    assert result[0] == projects.PythonProject(name="repo-tasks", path=Path(), version="0.1.0")


def test_discover_python_projects_no_workspace_table_means_root_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text(_ROOT_PYPROJECT)
    c = MockContext(run=True)
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0")
    ]


def test_discover_python_projects_resolves_workspace_member_globs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_workspace_root(tmp_path, '["examples/*"]')
    _write_member(tmp_path, "examples/beta", "beta", "0.2.0")
    _write_member(tmp_path, "examples/alpha", "alpha", "0.1.0")
    c = MockContext(run=True)
    # Root first, then members sorted — callers index [0] for "the repo's own project".
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0"),
        projects.PythonProject(name="alpha", path=Path("examples/alpha"), version="0.1.0"),
        projects.PythonProject(name="beta", path=Path("examples/beta"), version="0.2.0"),
    ]


def test_discover_python_projects_honours_workspace_exclude(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_workspace_root(tmp_path, '["examples/*"]', exclude='["examples/skipped"]')
    _write_member(tmp_path, "examples/kept", "kept", "0.1.0")
    _write_member(tmp_path, "examples/skipped", "skipped", "0.1.0")
    c = MockContext(run=True)
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "kept"]


def test_discover_python_projects_skips_member_dir_without_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_workspace_root(tmp_path, '["examples/*"]')
    _write_member(tmp_path, "examples/real", "real", "0.1.0")
    (tmp_path / "examples" / "not-a-project").mkdir()
    c = MockContext(run=True)
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "real"]


def test_discover_python_projects_allows_a_table_less_workspace_root(tmp_path, monkeypatch):
    """uv's "virtual" workspace root — a pyproject.toml that only groups members, no [project]."""
    monkeypatch.chdir(tmp_path)
    _write_workspace_root(tmp_path, '["examples/*"]', project="")
    _write_member(tmp_path, "examples/only", "only", "0.1.0")
    c = MockContext(run=True)
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="only", path=Path("examples/only"), version="0.1.0")
    ]


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


def test_discover_helm_charts_empty_with_no_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = MockContext(run=True)
    assert projects.discover_helm_charts(c) == []


def test_discover_helm_charts_reads_explicit_repo_tasks_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repo-tasks.toml").write_text(
        "[[helm]]\n"
        'name = "sample-service-chart"\n'
        'path = "examples/sample-service/chart"\n'
        'registry = "oci://ghcr.io/org/charts"\n'
        'group = "sample-service"\n'
    )
    c = MockContext(run=True)
    assert projects.discover_helm_charts(c) == [
        projects.HelmChart(
            name="sample-service-chart",
            path=Path("examples/sample-service/chart"),
            registry="oci://ghcr.io/org/charts",
            group="sample-service",
        )
    ]


def test_discover_helm_charts_registry_optional_and_group_defaults_to_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repo-tasks.toml").write_text('[[helm]]\nname = "solo-chart"\npath = "chart"\n')
    c = MockContext(run=True)
    result = projects.discover_helm_charts(c)
    assert result == [projects.HelmChart(name="solo-chart", path=Path("chart"), registry=None, group="solo-chart")]
