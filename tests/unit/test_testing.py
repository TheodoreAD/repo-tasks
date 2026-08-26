"""Tests for repo_tasks.testing: the exact command each tier's task builds, the exit-code
contracts, and the no-op-when-absent behaviour of the integration targets.

The `c` fixture from conftest is deliberately not used where a specific exit code is under test —
those cases need `MockContext(run=Result(exited=...))`, which is the split that fixture's docstring
describes."""

import shutil
from pathlib import Path

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import quality, testing


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
    """A src-layout package with one module, and optionally the unit test for it.

    The module carries a real statement, not an empty file: `untested_modules` skips a module with
    no code in it, so an empty one would make every "must report this as missing" case below pass
    for the wrong reason. Tests about that skip overwrite the file themselves."""
    package = root / "src" / "pkg"
    package.mkdir(parents=True, exist_ok=True)
    (package / module).write_text("VALUE = 1\n")
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


@pytest.mark.parametrize(
    "source",
    ['"""Just a description."""\n', "", "\n\n# a comment only\n"],
    ids=["docstring-only", "empty", "comment-only"],
)
def test_untested_modules_skips_a_module_with_no_code(c, tmp_cwd, source: str):
    # A generated project's __init__.py is often exactly its own docstring. Demanding a
    # test_init.py for it buys a placeholder assertion in every repo, not coverage — found by
    # scaffoldapy's e2e tier, where all ten rendered combinations failed on it.
    _write_module_and_test(tmp_cwd, "__init__.py", None)
    (tmp_cwd / "src" / "pkg" / "__init__.py").write_text(source)
    testing.untested_modules.body(c)


def test_untested_modules_still_wants_a_test_for_a_re_exporting_init(c, tmp_cwd):
    # The other side of the same rule: an __all__ or a re-export is a contract someone depends on,
    # which is what this package's own __init__.py is.
    _write_module_and_test(tmp_cwd, "__init__.py", None)
    (tmp_cwd / "src" / "pkg" / "__init__.py").write_text('from .thing import ns\n\n__all__ = ["ns"]\n')
    with pytest.raises(Exit):
        testing.untested_modules.body(c)


def test_untested_modules_treats_an_unparseable_module_as_needing_a_test(c, tmp_cwd):
    # Silently reporting a broken file as "nothing to test" would hide it, and finding syntax
    # errors is the linter's job, not this check's.
    _write_module_and_test(tmp_cwd, "thing.py", None)
    (tmp_cwd / "src" / "pkg" / "thing.py").write_text("def (\n")
    with pytest.raises(Exit):
        testing.untested_modules.body(c)


def test_untested_modules_noops_without_a_src_layout(c, tmp_cwd, capsys):
    # A flat-layout consumer is not doing anything wrong — same safe-to-run-unconditionally
    # contract as shell_check and workflow_check.
    testing.untested_modules.body(c)
    assert "nothing to do" in capsys.readouterr().out


def test_coverage_scopes_to_each_package_under_src(c, tmp_cwd):
    _write_module_and_test(tmp_cwd, "__init__.py", "test_init.py")
    (tmp_cwd / "src" / "other").mkdir()
    (tmp_cwd / "src" / "other" / "__init__.py").write_text("")
    testing.coverage.body(c)
    c.run.assert_called_once_with("pytest --cov=other --cov=pkg --cov-report=term-missing", echo=True, warn=True)


def test_coverage_falls_back_to_the_working_directory_without_a_src_layout(c, tmp_cwd):
    # A flat project still wants a number; only the scoping differs.
    testing.coverage.body(c)
    c.run.assert_called_once_with("pytest --cov=. --cov-report=term-missing", echo=True, warn=True)


def test_coverage_adds_the_html_report_on_request(c, tmp_cwd):
    testing.coverage.body(c, html=True)
    c.run.assert_called_once_with("pytest --cov=. --cov-report=term-missing --cov-report=html", echo=True, warn=True)


def test_coverage_never_sets_a_threshold(c, tmp_cwd):
    # Report, not gate. This tier asserts on mocked command strings, so the number measures how
    # much mocking got written; test.untested-modules is the half with a true answer, and the half
    # in quality.check.
    testing.coverage.body(c, html=True)
    assert "--cov-fail-under" not in c.run.call_args[0][0]


def test_coverage_is_not_a_gate_step():
    assert testing.coverage not in quality.check.pre


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
