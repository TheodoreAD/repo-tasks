"""Tests for repo_tasks.testing: the exact command each tier's task builds, the exit-code
contracts, and the no-op-when-absent behaviour of the integration targets.

The `c` fixture from conftest is deliberately not used where a specific exit code is under test —
those cases need `MockContext(run=Result(exited=...))`, which is the split that fixture's docstring
describes."""

import shutil
from pathlib import Path

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import testing


@pytest.fixture
def integration_dir(tmp_cwd: Path) -> Path:
    """A repo whose tests/integration directory exists, since the integration targets check for it
    before naming it on a command line. Builds on tmp_cwd so the chdir is not repeated here."""
    (tmp_cwd / "tests" / "integration").mkdir(parents=True)
    return tmp_cwd


def test_unit_runs_a_bare_pytest_and_names_no_path():
    """Naming a path would defeat pytest's own testpaths fallback — an explicit path that doesn't
    exist is a hard exit-4 usage error, where a missing testpaths entry is only a warning."""
    c = MockContext(run=Result(exited=0))
    testing.unit.body(c)
    c.run.assert_called_once_with("pytest", echo=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_unit_noops_cleanly_when_no_tests_collected():
    # pytest's own exit code 5 — the same safe-to-run-unconditionally contract shell_check has,
    # needed for a quality-gates-only repo with no python tests at all to pass `check`.
    c = MockContext(run=Result(exited=5))
    testing.unit.body(c)  # must not raise


def test_unit_reraises_real_failures():
    c = MockContext(run=Result(exited=1))
    with pytest.raises(Exit) as exc_info:
        testing.unit.body(c)
    assert exc_info.value.code == 1


def test_integration_runs_the_whole_tier(c, integration_dir):
    testing.integration.body(c)
    c.run.assert_called_once_with("pytest tests/integration", echo=True, warn=True)


def test_smoke_filters_on_the_marker(c, integration_dir):
    testing.smoke.body(c)
    c.run.assert_called_once_with("pytest tests/integration -m smoke", echo=True, warn=True)


def test_regression_is_the_inverse_of_smoke(c, integration_dir):
    testing.regression.body(c)
    c.run.assert_called_once_with('pytest tests/integration -m "not smoke"', echo=True, warn=True)


@pytest.mark.parametrize("task_name", ["integration", "smoke", "regression"])
def test_integration_targets_noop_without_a_tier(c, task_name, tmp_cwd, capsys):
    """Not decoration: unlike `unit`, these name a path, and pytest exits 4 on one that isn't
    there. Same contract as quality.shell_check and helm.py in a repo lacking the artifact."""
    getattr(testing, task_name).body(c)  # pyright: ignore[reportAny]
    assert "nothing to do" in capsys.readouterr().out
    c.run.assert_not_called()


@pytest.fixture
def workflows_dir(tmp_cwd: Path) -> Path:
    (tmp_cwd / ".github" / "workflows").mkdir(parents=True)
    return tmp_cwd


def test_workflows_runs_act_for_the_push_event_by_default(c, workflows_dir):
    testing.workflows.body(c)
    c.run.assert_called_once_with("act push", echo=True)


def test_workflows_passes_job_event_and_dry_run_through(c, workflows_dir):
    testing.workflows.body(c, job="quality", event="pull_request", dry_run=True)
    c.run.assert_called_once_with("act pull_request -j quality -n", echo=True)


def test_workflows_noops_without_a_workflows_dir(c, tmp_cwd, capsys):
    testing.workflows.body(c)
    assert "nothing to do" in capsys.readouterr().out
    c.run.assert_not_called()


def _write_module_and_test(root: Path, module: str, test: str | None) -> None:
    package = root / "src" / "pkg"
    package.mkdir(parents=True, exist_ok=True)
    (package / module).write_text("")
    unit_dir = root / "tests" / "unit"
    unit_dir.mkdir(parents=True, exist_ok=True)
    if test is not None:
        (unit_dir / test).write_text("")


def test_untested_modules_passes_when_every_module_has_a_test(c, tmp_cwd):
    _write_module_and_test(tmp_cwd, "thing.py", "test_thing.py")
    testing.untested_modules.body(c)


def test_untested_modules_names_the_module_and_the_file_it_wants(c, tmp_cwd, capsys):
    _write_module_and_test(tmp_cwd, "thing.py", None)
    with pytest.raises(Exit) as exc_info:
        testing.untested_modules.body(c)
    assert exc_info.value.code == 1
    assert "src/pkg/thing.py has no tests/unit/test_thing.py" in capsys.readouterr().out


def test_untested_modules_maps_dunder_init_to_test_init(c, tmp_cwd):
    # test___init__.py reads badly and nobody writes it; this package and every consumer already
    # call it test_init.py.
    _write_module_and_test(tmp_cwd, "__init__.py", "test_init.py")
    testing.untested_modules.body(c)


def test_untested_modules_noops_without_a_src_layout(c, tmp_cwd, capsys):
    # A flat-layout consumer is not doing anything wrong — same safe-to-run-unconditionally
    # contract as shell_check and workflow_check.
    testing.untested_modules.body(c)
    assert "nothing to do" in capsys.readouterr().out


def test_unit_preflights_pytest_itself(monkeypatch):
    # `unit` runs inside quality.check, so a dev group behind the repo-tasks-quality manifest hits
    # this the same way it hits quality.py's tools — and gets the same fix rather than exit 127.
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    c = MockContext(run=Result(exited=0))
    with pytest.raises(Exit):
        testing.unit.body(c)
    c.run.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]


def test_integration_dir_constant_matches_the_repos_own_layout():
    assert Path("tests/integration") == testing._INTEGRATION_DIR


def test_all_chains_unit_then_the_integration_tier():
    assert [t.name for t in testing.all.pre] == ["unit", "integration"]
