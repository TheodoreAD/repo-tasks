"""Tests for repo_tasks.version: dedicated coverage for _bumpversion_config (the one piece of real
logic — the per-group config bump-my-version actually reads) plus bump's overall command shape,
following test_quality.py's existing MockContext style."""

import subprocess
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
    assert "search = 'version: {current_version}'" in config
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
    ("current", "part", "rc", "expected"),
    [
        # major/minor/patch land on rc1 — bump-my-version's own arithmetic once pre_l exists —
        # unless the caller asks for the final outright (a hotfix), which _bump states as
        # --new-version. tests/integration pins every row here against `show --increment`.
        ("1.2.3", "major", True, "2.0.0rc1"),
        ("1.2.3", "minor", True, "1.3.0rc1"),
        ("1.2.3", "patch", True, "1.2.4rc1"),
        ("1.2.3", "major", False, "2.0.0"),
        ("1.2.3", "minor", False, "1.3.0"),
        ("1.2.3", "patch", False, "1.2.4"),
        ("1.3.0rc2", "minor", True, "1.4.0rc1"),
        ("1.3.0rc1", "rc", True, "1.3.0rc2"),
        ("1.3.0rc9", "rc", True, "1.3.0rc10"),
        ("1.3.0rc3", "final", True, "1.3.0"),
    ],
)
def test_next_version_transitions(current, part, rc, expected):
    assert version.next_version(current, part, rc=rc) == expected


@pytest.mark.parametrize(
    ("current", "part", "match"),
    [
        ("1.2.3", "bogus", "bogus"),
        ("1.2.3", "rc", "final version"),
        ("1.2.3", "final", "already final"),
        ("1.2.4.dev5+gabc1234", "patch", "dev build"),
    ],
)
def test_next_version_refuses_impossible_transitions(current, part, match):
    with pytest.raises(ValueError, match=match):
        version.next_version(current, part)


# ---------------------------------------------------------------------------
# Version — parts in, one spelling per artifact kind out
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pep440", "semver"),
    [
        ("1.2.3", "1.2.3"),
        ("1.2.3rc1", "1.2.3-rc.1"),
        ("1.2.4.dev5+gabc1234", "1.2.4-dev.5.gabc1234"),
        ("1.3.0rc2.dev1+g81b8701", "1.3.0-rc.2.dev.1.g81b8701"),
    ],
)
def test_version_round_trips_pep440_and_spells_semver(pep440, semver):
    v = version.Version.parse(pep440)
    assert v.pep440() == pep440
    assert v.semver() == semver
    assert version.semver(pep440) == semver


@pytest.mark.parametrize("text", ["1.2", "1.2.3a1", "1.2.3b2", "1.2.3.post1", "1!1.2.3", "1.2.3+local", "v1.2.3"])
def test_version_rejects_shapes_this_package_never_writes(text):
    with pytest.raises(ValueError, match="unsupported version"):
        version.Version.parse(text)


def test_version_is_final_only_without_rc_or_dev():
    assert version.Version.parse("1.2.3").is_final
    assert not version.Version.parse("1.2.3rc1").is_final
    assert not version.Version.parse("1.2.4.dev1+gabc1234").is_final


# ---------------------------------------------------------------------------
# bump — the rc cycle and the straight-to-final hotfix path
# ---------------------------------------------------------------------------


def test_bumpversion_config_declares_the_rc_scheme():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    chart = projects.HelmChart(name="sample-chart", path=Path("chart"), registry=None, group="sample")
    config = version._bumpversion_config(project, charts=[chart], tag=True)
    data = tomllib.loads(config)["tool"]["bumpversion"]  # pyright: ignore[reportAny]
    assert data["parts"]["pre_l"] == {"values": ["rc", "final"], "optional_value": "final"}
    assert data["parts"]["pre_n"] == {"first_value": "1"}
    assert data["serialize"] == ["{major}.{minor}.{patch}{pre_l}{pre_n}", "{major}.{minor}.{patch}"]
    files: list[dict[str, object]] = data["files"]  # pyright: ignore[reportAny]
    # Only the chart entries spell the version as SemVer; pyproject.toml inherits the global.
    assert [f.get("serialize") for f in files] == [
        None,
        ["{major}.{minor}.{patch}-{pre_l}.{pre_n}", "{major}.{minor}.{patch}"],
        ["{major}.{minor}.{patch}-{pre_l}.{pre_n}", "{major}.{minor}.{patch}"],
    ]


@pytest.mark.parametrize(
    ("part", "rc", "expected_tail"),
    [
        ("minor", True, "bump minor --config-file "),
        ("rc", True, "bump pre_n --config-file "),
        ("final", True, "bump pre_l --config-file "),
    ],
)
def test_bump_maps_parts_onto_bumpversion_components(c, part, rc, expected_tail):
    version.bump.body(c, part=part, rc=rc)
    command = c.run.call_args_list[0][0][0]
    assert command.startswith(f"bump-my-version {expected_tail}")
    assert "--new-version" not in command


def test_bump_states_the_final_version_outright_when_rc_is_off(c):
    # bump-my-version's own arithmetic can only land on rc1; the hotfix path names the final.
    version.bump.body(c, part="patch", rc=False)
    command = c.run.call_args_list[0][0][0]
    assert command.startswith("bump-my-version bump patch --config-file ")
    assert command.endswith(" --new-version 0.1.1")


def test_bump_raises_for_an_unknown_part(c):
    with pytest.raises(ValueError, match="bogus"):
        version.bump.body(c, part="bogus")
    c.run.assert_not_called()


# ---------------------------------------------------------------------------
# set_dev — the working-tree rewrite behind every --dev flag
# ---------------------------------------------------------------------------


_DEV_LOCK = '[[package]]\nname = "sample"\nversion = "1.0.0"\n\n[[package]]\nname = "dep"\nversion = "1.0.0"\n'
_DEV_CHART = 'apiVersion: v2\nname: sample\nversion: 1.0.0\nappVersion: "1.0.0"\n'


def _dev_tree(tmp_cwd: Path, chart: bool = True):
    (tmp_cwd / "pyproject.toml").write_text('[project]\nname = "sample"\nversion = "1.0.0"\n')
    (tmp_cwd / "uv.lock").write_text(_DEV_LOCK)
    if chart:
        (tmp_cwd / "chart").mkdir()
        (tmp_cwd / "chart" / "Chart.yaml").write_text(_DEV_CHART)


def _stub_dev(monkeypatch, dirty: str = ""):
    monkeypatch.setattr(version, "_dev_version", lambda: version.Version.parse("1.0.1.dev3+gabc1234"))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=dirty, stderr=""))
    project = projects.PythonProject(name="sample", path=Path(), version="1.0.0")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [project])


def test_set_dev_rewrites_every_file_in_the_group_without_committing(c, tmp_cwd, monkeypatch, capsys):
    _dev_tree(tmp_cwd)
    _stub_dev(monkeypatch)
    chart = projects.HelmChart(name="sample", path=Path("chart"), registry=None, group="sample")
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [chart])

    assert version.set_dev.body(c) == "1.0.1.dev3+gabc1234"

    assert 'version = "1.0.1.dev3+gabc1234"' in (tmp_cwd / "pyproject.toml").read_text()
    lock = (tmp_cwd / "uv.lock").read_text()
    assert 'name = "sample"\nversion = "1.0.1.dev3+gabc1234"' in lock
    assert 'name = "dep"\nversion = "1.0.0"' in lock  # the anchor kept the dependency alone
    chart_text = (tmp_cwd / "chart" / "Chart.yaml").read_text()
    assert "version: 1.0.1-dev.3.gabc1234" in chart_text
    assert 'appVersion: "1.0.1-dev.3.gabc1234"' in chart_text
    c.run.assert_not_called()  # nothing shells out through invoke — no bump-my-version, no commit
    assert "git restore pyproject.toml uv.lock chart/Chart.yaml chart/Chart.yaml" in capsys.readouterr().out


def test_set_dev_refuses_a_dirty_tree(c, tmp_cwd, monkeypatch):
    _dev_tree(tmp_cwd)
    _stub_dev(monkeypatch, dirty=" M pyproject.toml\n")
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])
    with pytest.raises(ValueError, match="dirty"):
        version.set_dev.body(c)
    assert 'version = "1.0.0"' in (tmp_cwd / "pyproject.toml").read_text()


def test_set_dev_fails_loudly_when_a_search_string_is_absent(c, tmp_cwd, monkeypatch):
    _dev_tree(tmp_cwd)
    (tmp_cwd / "chart" / "Chart.yaml").write_text("apiVersion: v2\nname: sample\nversion: 1.0.0\nappVersion: 1.0.0\n")
    _stub_dev(monkeypatch)
    chart = projects.HelmChart(name="sample", path=Path("chart"), registry=None, group="sample")
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [chart])
    with pytest.raises(ValueError, match="did not find"):
        version.set_dev.body(c)
