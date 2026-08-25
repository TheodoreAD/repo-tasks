"""Real, non-mocked group bump: runs bump-my-version against a throwaway git repo holding a
pyproject.toml plus a Chart.yaml copied verbatim from this repo's own dogfood chart, and asserts
all three version fields moved in one commit and one tag.

tests/test_version.py already pins the *generated config* — the one piece of real logic — but the
chart half of a bump had never actually been executed: whether bump-my-version finds those exact
search strings in a real Chart.yaml was an assumption. This is the tier that settles it.

Needs neither Docker nor devpi-server, unlike its siblings here — bump-my-version is a runtime
dependency of this package, so this module never skips. It lives in the integration tier anyway
because it shells out for real (git commits, git tags, a subprocess), which is precisely what the
unit tier promises not to do.
"""

import subprocess
from pathlib import Path

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

    version.bump.body(c, part="minor", group="sample-service")

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

    version.bump.body(c, part="patch")

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

    version.bump.body(c, part="minor", group="svc")

    lock_text = (tmp_path / "uv.lock").read_text()
    assert 'name = "svc"\nversion = "0.2.0"' in lock_text
    assert 'name = "root"\nversion = "0.1.0"' in lock_text
    assert 'version = "0.1.0"' in (tmp_path / "pyproject.toml").read_text()
    check = _uv(tmp_path, "lock", "--check")
    assert check.returncode == 0, check.stderr


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

    version.bump.body(c, part="patch", group="sample-service")

    assert 'version = "0.1.1"' in (tmp_path / "pyproject.toml").read_text()
    assert "version: 0.1.0" in (chart_dir / "Chart.yaml").read_text()
