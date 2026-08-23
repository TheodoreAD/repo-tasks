"""Tests for repo_tasks.testing: the exact command each tier's task builds, the exit-code
contracts, and the no-op-when-absent behaviour of the integration targets.

The `c` fixture from conftest is deliberately not used where a specific exit code is under test —
those cases need `MockContext(run=Result(exited=...))`, which is the split that fixture's docstring
describes."""

from pathlib import Path

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import testing


@pytest.fixture
def integration_dir(tmp_path, monkeypatch):
    """A repo whose tests/integration directory exists, since the integration targets check for it
    before naming it on a command line."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests" / "integration").mkdir(parents=True)
    return tmp_path


def test_unit_runs_a_bare_pytest_and_names_no_path():
    """Naming a path would defeat pytest's own testpaths fallback — an explicit path that doesn't
    exist is a hard exit-4 usage error, where a missing testpaths entry is only a warning."""
    c = MockContext(run=Result(exited=0))
    testing.unit.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("pytest", echo=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_unit_noops_cleanly_when_no_tests_collected():
    # pytest's own exit code 5 — the same safe-to-run-unconditionally contract shell_check has,
    # needed for a quality-gates-only repo with no python tests at all to pass `check`.
    c = MockContext(run=Result(exited=5))
    testing.unit.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess] — must not raise


def test_unit_reraises_real_failures():
    c = MockContext(run=Result(exited=1))
    with pytest.raises(Exit) as exc_info:
        testing.unit.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert exc_info.value.code == 1


def test_integration_runs_the_whole_tier(c, integration_dir):
    testing.integration.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("pytest tests/integration", echo=True, warn=True)


def test_smoke_filters_on_the_marker(c, integration_dir):
    testing.smoke.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("pytest tests/integration -m smoke", echo=True, warn=True)


def test_regression_is_the_inverse_of_smoke(c, integration_dir):
    testing.regression.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with('pytest tests/integration -m "not smoke"', echo=True, warn=True)


@pytest.mark.parametrize("task_name", ["integration", "smoke", "regression"])
def test_integration_targets_noop_without_a_tier(task_name, tmp_path, monkeypatch, capsys):
    """Not decoration: unlike `unit`, these name a path, and pytest exits 4 on one that isn't
    there. Same contract as quality.shell_check and helm.py in a repo lacking the artifact."""
    monkeypatch.chdir(tmp_path)
    c = MockContext(run=True)
    getattr(testing, task_name).body(c)  # pyright: ignore[reportAny]
    assert "nothing to do" in capsys.readouterr().out
    c.run.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]


def test_integration_dir_constant_matches_the_repos_own_layout():
    assert Path("tests/integration") == testing._INTEGRATION_DIR  # pyright: ignore[reportPrivateUsage]


def test_all_chains_unit_then_the_integration_tier():
    assert [t.name for t in testing.all.pre] == ["unit", "integration"]  # pyright: ignore[reportAny, reportFunctionMemberAccess]
