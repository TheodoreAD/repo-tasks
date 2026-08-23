"""Tests for repo_tasks.version: dedicated coverage for _bumpversion_config (the one piece of real
logic — the per-group config bump-my-version actually reads) plus bump's overall command shape,
following test_quality.py's existing MockContext style."""

from pathlib import Path

import pytest

from repo_tasks import projects, version


def test_bumpversion_config_targets_the_project_pyproject_and_current_version():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=True)  # pyright: ignore[reportPrivateUsage] — testing the one piece of real logic directly
    assert 'current_version = "0.1.0"' in config
    assert 'filename = "pyproject.toml"' in config
    assert 'tag_name = "v{new_version}"' in config
    assert "Chart.yaml" not in config


def test_bumpversion_config_omits_tag_when_tag_is_false():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, charts=[], tag=False)  # pyright: ignore[reportPrivateUsage]
    assert "tag = false" in config
    assert "tag_name" not in config


def test_bumpversion_config_bumps_chart_version_and_quoted_app_version():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    chart = projects.HelmChart(name="sample-chart", path=Path("chart"), registry=None, group="sample")
    config = version._bumpversion_config(project, charts=[chart], tag=True)  # pyright: ignore[reportPrivateUsage]
    assert config.count('filename = "chart/Chart.yaml"') == 2
    assert 'search = "version: {current_version}"' in config
    assert "search = 'appVersion: \"{current_version}\"'" in config


def test_bump_includes_only_charts_sharing_the_bumped_group(c, monkeypatch):
    charts = [
        projects.HelmChart(name="repo-tasks-chart", path=Path("chart"), registry=None, group="repo-tasks"),
        projects.HelmChart(name="other-chart", path=Path("other"), registry=None, group="other"),
    ]
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: charts)
    seen = {}

    def _capture(project, charts, tag):
        seen["charts"] = charts
        return original_config(project, charts, tag)

    original_config = version._bumpversion_config  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(version, "_bumpversion_config", _capture)
    version.bump.body(c, part="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert [chart.name for chart in seen["charts"]] == ["repo-tasks-chart"]


def test_bump_invokes_bumpversion_with_a_generated_config_file_and_returns_new_version(c):
    result = version.bump.body(c, part="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]

    call_args = c.run.call_args_list[0]
    command = call_args[0][0]
    assert command.startswith("bump-my-version bump minor --config-file ")
    assert call_args[1] == {"echo": True}

    config_path = Path(command.removeprefix("bump-my-version bump minor --config-file "))
    assert not config_path.exists()  # cleaned up after the run

    assert result == "0.1.0"  # MockContext never really runs bump-my-version, so the file is unchanged


def test_bump_raises_for_an_unknown_group(c):
    with pytest.raises(ValueError, match="no-such-project"):
        version.bump.body(c, part="minor", group="no-such-project")  # pyright: ignore[reportAny, reportFunctionMemberAccess]


def test_current_version_reads_the_resolved_projects_version(c):
    assert version.current_version(c) == "0.1.0"


def test_current_version_raises_for_an_unknown_group(c):
    with pytest.raises(ValueError, match="no-such-project"):
        version.current_version(c, group="no-such-project")


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
