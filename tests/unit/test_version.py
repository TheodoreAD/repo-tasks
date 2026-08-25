"""Tests for repo_tasks.version: dedicated coverage for _bumpversion_config (the one piece of real
logic — the per-group config bump-my-version actually reads) plus bump's overall command shape,
following test_quality.py's existing MockContext style."""

import tomllib
from pathlib import Path

import pytest

from repo_tasks import projects, version


def test_bumpversion_config_targets_the_project_pyproject_and_current_version():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=True)  # testing the one piece of real logic directly
    assert 'current_version = "0.1.0"' in config
    assert 'filename = "pyproject.toml"' in config
    assert 'tag_name = "v{new_version}"' in config
    assert "Chart.yaml" not in config


def test_bumpversion_config_omits_tag_when_tag_is_false():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=False)
    assert "tag = false" in config
    assert "tag_name" not in config


def test_bumpversion_config_bumps_chart_version_and_quoted_app_version():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    chart = projects.HelmChart(name="sample-chart", path=Path("chart"), registry=None, group="sample")
    config = version._bumpversion_config(project, charts=[chart], tag=True)
    assert config.count('filename = "chart/Chart.yaml"') == 2
    assert 'search = "version: {current_version}"' in config
    assert "search = 'appVersion: \"{current_version}\"'" in config


def test_bumpversion_config_without_a_lock_never_mentions_uv():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=True)
    assert "uv.lock" not in config
    assert "pre_commit_hooks" not in config


def test_bumpversion_config_rewrites_the_lock_anchored_on_the_project_name_and_checks_it():
    # uv.lock spells this project's version exactly like every dependency's, so the search is
    # anchored on the `name = ...` line uv writes immediately before it — and `uv lock --check`
    # runs before the commit so a misfire fails the bump rather than shipping a stale lock.
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=True, lock_path=Path("uv.lock"))
    assert 'filename = "uv.lock"' in config
    assert 'search = "name = \\"sample\\"\\nversion = \\"{current_version}\\""' in config
    assert 'replace = "name = \\"sample\\"\\nversion = \\"{new_version}\\""' in config
    assert 'pre_commit_hooks = ["uv lock --check"]' in config
    # The generated file is TOML bump-my-version has to parse: the `\n` must survive as a real
    # newline, which only a basic (double-quoted) string gives.
    files: list[dict[str, str]] = tomllib.loads(config)["tool"]["bumpversion"]["files"]  # pyright: ignore[reportAny]
    lock_entry = next(f for f in files if f["filename"] == "uv.lock")
    assert lock_entry["search"] == 'name = "sample"\nversion = "{current_version}"'


def test_bump_passes_the_root_lock_only_when_it_exists(c, tmp_cwd, monkeypatch):
    seen = {}

    def _capture(project, charts, tag, lock_path=None):
        seen["lock_path"] = lock_path
        return original_config(project, charts, tag, lock_path=lock_path)

    original_config = version._bumpversion_config
    monkeypatch.setattr(version, "_bumpversion_config", _capture)
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])
    project = projects.PythonProject(name="sample", path=Path("svc"), version="0.1.0")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [project])

    version.bump.body(c, part="patch")
    assert seen["lock_path"] is None

    # The workspace root's lock, never one under the member's own path.
    (tmp_cwd / "uv.lock").write_text("")
    version.bump.body(c, part="patch")
    assert seen["lock_path"] == Path("uv.lock")


def test_bump_includes_only_charts_sharing_the_bumped_group(c, monkeypatch):
    charts = [
        projects.HelmChart(name="repo-tasks-chart", path=Path("chart"), registry=None, group="repo-tasks"),
        projects.HelmChart(name="other-chart", path=Path("other"), registry=None, group="other"),
    ]
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: charts)
    seen = {}

    def _capture(project, charts, tag, lock_path=None):
        seen["charts"] = charts
        return original_config(project, charts, tag, lock_path=lock_path)

    original_config = version._bumpversion_config
    monkeypatch.setattr(version, "_bumpversion_config", _capture)
    version.bump.body(c, part="minor")
    assert [chart.name for chart in seen["charts"]] == ["repo-tasks-chart"]


def test_bump_invokes_bumpversion_with_a_generated_config_file_and_returns_new_version(c):
    result = version.bump.body(c, part="minor")

    call_args = c.run.call_args_list[0]
    command = call_args[0][0]
    assert command.startswith("bump-my-version bump minor --config-file ")
    assert call_args[1] == {"echo": True}

    config_path = Path(command.removeprefix("bump-my-version bump minor --config-file "))
    assert not config_path.exists()  # cleaned up after the run

    assert result == "0.1.0"  # MockContext never really runs bump-my-version, so the file is unchanged


def test_bump_raises_for_an_unknown_group(c):
    with pytest.raises(ValueError, match="no-such-project"):
        version.bump.body(c, part="minor", group="no-such-project")


def test_current_version_reads_the_resolved_projects_version(c):
    assert version.current_version(c) == "0.1.0"


def test_current_version_raises_for_an_unknown_group(c):
    with pytest.raises(ValueError, match="no-such-project"):
        version.current_version(c, group="no-such-project")


def test_current_version_raises_clearly_with_no_python_project(c, tmp_cwd):
    # A Dockerfile-only repo reaches this through docker.build's default tag — a ValueError that
    # names the cause, never an IndexError out of `[0]` or a FileNotFoundError from discovery.
    with pytest.raises(ValueError, match="no python project found"):
        version.current_version(c)


@pytest.mark.parametrize(
    ("part", "expected"),
    [
        ("major", "2.0.0"),
        ("minor", "1.3.0"),
        ("patch", "1.2.4"),
    ],
)
def test_next_version_bumps_the_requested_part_and_resets_lower_parts(part, expected):
    assert version.next_version("1.2.3", part) == expected


def test_next_version_raises_for_an_unknown_part():
    with pytest.raises(ValueError, match="bogus"):
        version.next_version("1.2.3", "bogus")
