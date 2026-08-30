"""Real, non-mocked group bump: runs bump-my-version against a throwaway git repo holding a
pyproject.toml plus a Chart.yaml copied verbatim from this repo's own dogfood chart, and asserts
all three version fields moved in one commit and one tag.

tests/test_version.py already pins the *generated config* — the one piece of real logic — but the
chart half of a bump had never actually been executed: whether bump-my-version finds those exact
search strings in a real Chart.yaml was an assumption. This is the tier that settles it.

Needs neither Docker nor a package index, unlike its siblings here — bump-my-version is a runtime
dependency of this package, so this module never skips. It lives in the integration tier anyway
because it shells out for real (git commits, git tags, a subprocess), which is precisely what the
unit tier promises not to do.
"""

import subprocess
from pathlib import Path

import pytest

from repo_tasks import version
from repo_tasks.projects import HelmChart, PythonProject


def _init_repo(root: Path) -> None:
    """A git repo bump-my-version can commit and tag into. Identity is set locally rather than
    inherited, so the test never depends on the machine's global git config."""
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_group_bump_moves_project_and_chart_together(c, tmp_path, monkeypatch, sample_chart_dir):
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    # The real dogfood Chart.yaml, not a hand-written stand-in: its `helm create` quoting is the
    # exact thing under test, and a paraphrase here could drift from the file that ships.
    (chart_dir / "Chart.yaml").write_text((sample_chart_dir / "Chart.yaml").read_text())
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "0.1.0"\n')
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    project = PythonProject(name="sample-service", path=Path(), version="0.1.0")
    chart = HelmChart(name="sample-service", path=Path("chart"), registry=None, group="sample-service")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [project])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [chart])

    version.bump.body(c, part="minor", group="sample-service", rc=False)

    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text()
    chart_text = (chart_dir / "Chart.yaml").read_text()
    assert "version: 0.2.0" in chart_text
    assert 'appVersion: "0.2.0"' in chart_text
    # One commit and one tag for the whole group — not one per file.
    assert _git(tmp_path, "tag", "--list") == "v0.2.0"
    assert _git(tmp_path, "rev-list", "--count", "HEAD") == "2"


_LOCKABLE_PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""


def _uv(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["uv", *args], cwd=root, check=False, capture_output=True, text=True)


def test_bump_relocks_in_the_same_commit(c, tmp_path, monkeypatch):
    # The regression this pins: uv.lock embeds the project's own version (astral-sh/uv#15643), so
    # a bump that only rewrote pyproject.toml left `uv lock --check` failing on a tree that looks
    # clean. The lock must move in the bump's own commit, and uv itself must accept the result.
    (tmp_path / "pyproject.toml").write_text(_LOCKABLE_PYPROJECT.format(name="probe"))
    assert _uv(tmp_path, "lock").returncode == 0
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    project = PythonProject(name="probe", path=Path(), version="0.1.0")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [project])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])

    version.bump.body(c, part="patch", rc=False)

    assert 'name = "probe"\nversion = "0.1.1"' in (tmp_path / "uv.lock").read_text()
    check = _uv(tmp_path, "lock", "--check")
    assert check.returncode == 0, check.stderr
    assert _git(tmp_path, "rev-list", "--count", "HEAD") == "2"
    assert "uv.lock" in _git(tmp_path, "show", "--stat", "--format=", "HEAD")
    assert _git(tmp_path, "status", "--porcelain") == ""


def test_workspace_member_bump_relocks_the_root_lock(c, tmp_path, monkeypatch):
    # A member has no lock of its own — its version sits in the root uv.lock next to every other
    # member's, which is exactly where a bare `version = "0.1.0"` search would hit the wrong one.
    root_pyproject = _LOCKABLE_PYPROJECT.format(name="root") + '\n[tool.uv.workspace]\nmembers = ["svc"]\n'
    (tmp_path / "pyproject.toml").write_text(root_pyproject)
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "pyproject.toml").write_text(_LOCKABLE_PYPROJECT.format(name="svc"))
    assert _uv(tmp_path, "lock").returncode == 0
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    member = PythonProject(name="svc", path=Path("svc"), version="0.1.0")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [member])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])

    version.bump.body(c, part="minor", group="svc", rc=False)

    lock_text = (tmp_path / "uv.lock").read_text()
    assert 'name = "svc"\nversion = "0.2.0"' in lock_text
    assert 'name = "root"\nversion = "0.1.0"' in lock_text
    assert 'version = "0.1.0"' in (tmp_path / "pyproject.toml").read_text()
    check = _uv(tmp_path, "lock", "--check")
    assert check.returncode == 0, check.stderr


_PROBE = PythonProject(name="probe", path=Path(), version="1.0.0")


def _rc_repo(tmp_path: Path, monkeypatch, sample_chart_dir: Path, start: str = "1.0.0"):
    """A project + the dogfood chart at `start`, with discovery pointed at them."""
    chart_dir = tmp_path / "chart"
    chart_dir.mkdir()
    chart_text = (sample_chart_dir / "Chart.yaml").read_text()
    chart_text = chart_text.replace("version: 0.1.0", f"version: {start}")
    (chart_dir / "Chart.yaml").write_text(chart_text.replace('appVersion: "0.1.0"', f'appVersion: "{start}"'))
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "sample-service"\nversion = "{start}"\n')
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    chart = HelmChart(name="sample-service", path=Path("chart"), registry=None, group="sample-service")
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [chart])
    # Re-read from disk on every call so each step sees the previous step's write.
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [_current_project(tmp_path)])


def _current_project(root: Path) -> PythonProject:
    text = (root / "pyproject.toml").read_text()
    return PythonProject(name="sample-service", path=Path(), version=text.split('version = "')[1].split('"')[0])


def _versions_on_disk(root: Path) -> tuple[str, str, str]:
    chart_text = (root / "chart" / "Chart.yaml").read_text()
    chart_version = next(line.split(": ", 1)[1] for line in chart_text.splitlines() if line.startswith("version:"))
    app_version = next(line.split(": ", 1)[1] for line in chart_text.splitlines() if line.startswith("appVersion:"))
    return _current_project(root).version, chart_version, app_version.strip('"')


def test_rc_cycle_spells_each_step_per_artifact_kind(c, tmp_path, monkeypatch, sample_chart_dir):
    """The whole candidate cycle for real: pyproject.toml in PEP 440, Chart.yaml in SemVer, one
    commit per step, and `show --increment` agreeing with next_version before every bump. This is
    the pin that makes the hand-rolled next_version safe (contributing/versioning.md)."""
    _rc_repo(tmp_path, monkeypatch, sample_chart_dir)
    steps = [
        ("minor", True, ("1.1.0rc1", "1.1.0-rc.1", "1.1.0-rc.1")),
        ("rc", True, ("1.1.0rc2", "1.1.0-rc.2", "1.1.0-rc.2")),
        ("rc", True, ("1.1.0rc3", "1.1.0-rc.3", "1.1.0-rc.3")),
        ("final", True, ("1.1.0", "1.1.0", "1.1.0")),
        ("patch", False, ("1.1.1", "1.1.1", "1.1.1")),
    ]
    for part, rc, expected in steps:
        current = _current_project(tmp_path).version
        predicted = version.next_version(current, part, rc=rc)
        if rc:
            # The pin: bump-my-version's own arithmetic on the config version.py generates.
            config = version._bumpversion_config(_current_project(tmp_path), charts=[], tag=False)
            config_path = tmp_path / "probe.toml"
            config_path.write_text(config)
            component = version._PARTS[part]
            shown = subprocess.run(
                ["bump-my-version", "show", "new_version", "--config-file", str(config_path), "--increment", component],
                check=True,
                capture_output=True,
                text=True,
                cwd=tmp_path,
            ).stdout.strip()
            config_path.unlink()
            assert shown == predicted, f"{part} from {current}"
        version.bump.body(c, part=part, group="sample-service", rc=rc)
        assert _versions_on_disk(tmp_path) == expected, f"{part} from {current}"
        assert predicted == expected[0]
    assert _git(tmp_path, "rev-list", "--count", "HEAD") == str(1 + len(steps))
    assert _git(tmp_path, "tag", "--list").splitlines() == ["v1.1.0", "v1.1.0rc1", "v1.1.0rc2", "v1.1.0rc3", "v1.1.1"]


def test_set_dev_writes_a_git_derived_version_and_uv_accepts_the_lock(c, tmp_path, monkeypatch):
    """A tree two commits past v1.0.0 becomes 1.0.1.dev2+g<sha> in pyproject.toml and uv.lock,
    uncommitted, and `uv lock --check` still passes — the lock's copy moved with the field."""
    (tmp_path / "pyproject.toml").write_text(_LOCKABLE_PYPROJECT.format(name="probe").replace('"0.1.0"', '"1.0.0"'))
    assert _uv(tmp_path, "lock").returncode == 0
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v1.0.0")
    for i in range(2):
        (tmp_path / f"f{i}").write_text(str(i))
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-m", f"commit {i}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [_PROBE])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])

    written = version.set_dev.body(c)

    sha = _git(tmp_path, "rev-parse", "--short=7", "HEAD")
    assert written == f"1.0.1.dev2+g{sha}"
    assert f'version = "1.0.1.dev2+g{sha}"' in (tmp_path / "pyproject.toml").read_text()
    assert f'name = "probe"\nversion = "1.0.1.dev2+g{sha}"' in (tmp_path / "uv.lock").read_text()
    check = _uv(tmp_path, "lock", "--check")
    assert check.returncode == 0, check.stderr
    modified = sorted(line.split()[-1] for line in _git(tmp_path, "status", "--porcelain").splitlines())
    assert modified == ["pyproject.toml", "uv.lock"]
    assert _git(tmp_path, "rev-list", "--count", "HEAD") == "3"  # nothing committed

    # A second run on the now-dirty tree refuses rather than rewriting the rewritten values.
    with pytest.raises(ValueError, match="dirty"):
        version.set_dev.body(c)


def test_set_dev_exactly_at_a_tag_is_that_release(c, tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "probe"\nversion = "1.0.0"\n')
    _init_repo(tmp_path)
    _git(tmp_path, "tag", "v1.0.0")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [_PROBE])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [])
    assert version.set_dev.body(c) == "1.0.0"
    assert _git(tmp_path, "status", "--porcelain") == ""


def test_group_bump_leaves_an_unrelated_groups_chart_alone(c, tmp_path, monkeypatch, sample_chart_dir):
    chart_dir = tmp_path / "other-chart"
    chart_dir.mkdir()
    (chart_dir / "Chart.yaml").write_text((sample_chart_dir / "Chart.yaml").read_text())
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "0.1.0"\n')
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    project = PythonProject(name="sample-service", path=Path(), version="0.1.0")
    other = HelmChart(name="other", path=Path("other-chart"), registry=None, group="something-else")
    monkeypatch.setattr(version, "discover_python_projects", lambda c: [project])
    monkeypatch.setattr(version, "discover_helm_charts", lambda c: [other])

    version.bump.body(c, part="patch", group="sample-service", rc=False)

    assert 'version = "0.1.1"' in (tmp_path / "pyproject.toml").read_text()
    assert "version: 0.1.0" in (chart_dir / "Chart.yaml").read_text()
