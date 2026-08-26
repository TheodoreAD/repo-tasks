"""Tests for repo_tasks.quality: asserts the exact command string each task
builds via invoke's MockContext, plus dedicated coverage for _sh_files — the
one piece of real logic, and what makes the mandatory `check`/`fix` composite
safe to run unconditionally on a repo with no shell scripts.

The command-string tests run against the real `shutil.which`, so they also assert that this repo's
own environment has every gate binary — which is the preflight's whole premise. The preflight's own
behaviour is covered in test_configs.py, where it lives; the tests here pin the wiring."""

import shutil
from collections.abc import Callable

import pytest
from invoke import Context, Exit, MockContext, Result, Task

from repo_tasks import deps, docs, quality, testing

# Every gate step under test here takes only the Context, so one alias covers the parametrized
# cases below — `Task` is generic over its body's signature in invoke-stubs. A plain assignment,
# not a `type` statement: this package supports 3.11, where that syntax does not exist.
GateStep = Task[Callable[[Context], None]]

_WORKFLOW_LISTING = (
    "git ls-files --cached --others --exclude-standard -- '.github/workflows/*.yml' '.github/workflows/*.yaml'"
)


def test_lint_check(c):
    quality.lint_check.body(c)
    c.run.assert_called_once_with("ruff check .", echo=True)


def test_lint_apply(c):
    quality.lint_apply.body(c)
    c.run.assert_called_once_with("ruff check --fix .", echo=True)


def test_format_check(c):
    quality.format_check.body(c)
    assert c.run.call_args_list == [
        (("ruff format --check .",), {"echo": True}),
        (("dprint check --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_format_apply(c):
    quality.format_apply.body(c)
    assert c.run.call_args_list == [
        (("ruff format .",), {"echo": True}),
        (("dprint fmt --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_type_check(c):
    quality.type_check.body(c)
    c.run.assert_called_once_with("basedpyright", echo=True)


def test_sh_files_empty():
    c = MockContext(run=Result(stdout="", exited=0))
    assert quality._sh_files(c) == []  # testing the one piece of real logic directly


def test_sh_files_nonempty():
    c = MockContext(run=Result(stdout="./a.sh ./b.sh\n", exited=0))
    assert quality._sh_files(c) == ["./a.sh", "./b.sh"]


def test_sh_files_command_failure_treated_as_empty():
    c = MockContext(run=Result(exited=1))
    assert quality._sh_files(c) == []


def test_shell_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_check.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_check_runs_shellcheck_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shellcheck ./a.sh": Result(exited=0),
        }
    )
    quality.shell_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shellcheck ./a.sh",),
        {"echo": True},
    )


def test_workflow_check_noop_when_no_workflow_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.workflow_check.body(c)
    c.run.assert_called_once_with(_WORKFLOW_LISTING, hide=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_workflow_check_runs_actionlint_when_files_found():
    c = MockContext(
        run={
            _WORKFLOW_LISTING: Result(stdout=".github/workflows/ci.yml\n", exited=0),
            "actionlint .github/workflows/ci.yml": Result(exited=0),
        }
    )
    quality.workflow_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("actionlint .github/workflows/ci.yml",),
        {"echo": True},
    )


def test_check_gates_on_workflow_check():
    assert "workflow_check" in [t.name for t in quality.check.pre]


def test_check_gates_on_link_check():
    # Retiring a plan deletes a file other documents link to; the procedure's "grep for inbound
    # references" step was honour-system until this ran in the gate.
    assert docs.link_check in quality.check.pre


def test_check_gates_on_untested_modules():
    # The question a coverage percentage cannot answer: which module has no tests at all.
    assert testing.untested_modules in quality.check.pre


def test_check_gates_on_lock_drift():
    # Without this, a pyproject.toml edit with no re-lock passes precommit and fails in CI, where
    # bootstrap.sh's `uv sync --locked` catches it. Deterministic and offline, unlike deps.audit.
    assert deps.check in quality.check.pre


def test_check_does_not_gate_on_audit():
    # The gate stays runnable offline: deps.audit queries OSV, so its result moves without the code.
    assert deps.audit not in quality.check.pre


def test_check_gates_on_shell_format_check():
    # The check-only half of shell formatting, so drift is caught by CI rather than only ever
    # surfaced by `fix` rewriting the file.
    assert "shell_format_check" in [t.name for t in quality.check.pre]


def test_shell_format_check_runs_shfmt_diff_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shfmt -d ./a.sh": Result(exited=0),
        }
    )
    quality.shell_format_check.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shfmt -d ./a.sh",),
        {"echo": True},
    )


def test_shell_format_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_check.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_format_apply_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_apply.body(c)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True
    )


def test_shell_format_apply_runs_shfmt_when_files_found():
    c = MockContext(
        run={
            "git ls-files --cached --others --exclude-standard -- '*.sh'": Result(stdout="./a.sh\n", exited=0),
            "shfmt -w ./a.sh": Result(exited=0),
        }
    )
    quality.shell_format_apply.body(c)
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shfmt -w ./a.sh",),
        {"echo": True},
    )


@pytest.mark.parametrize(
    "step",
    [quality.lint_check, quality.lint_apply, quality.format_check, quality.format_apply, quality.type_check],
)
def test_unconditional_steps_preflight_their_binary(c, monkeypatch, step: GateStep):
    # Exit, not the shell's exit 127 from a command that was never runnable — with the missing
    # entry and the command that adds it in the message (see test_configs.py for the text).
    monkeypatch.setattr(shutil, "which", lambda tool: None)
    with pytest.raises(Exit):
        step.body(c)
    c.run.assert_not_called()


_SH_LISTING = "git ls-files --cached --others --exclude-standard -- '*.sh'"


@pytest.mark.parametrize(
    ("step", "listing", "found"),
    [
        (quality.shell_check, _SH_LISTING, "./a.sh\n"),
        (quality.shell_format_check, _SH_LISTING, "./a.sh\n"),
        (quality.shell_format_apply, _SH_LISTING, "./a.sh\n"),
        (quality.workflow_check, _WORKFLOW_LISTING, ".github/workflows/ci.yml\n"),
    ],
)
def test_file_gated_steps_preflight_only_once_they_have_files(monkeypatch, step: GateStep, listing: str, found: str):
    monkeypatch.setattr(shutil, "which", lambda tool: None)

    # No files: still a clean no-op. The preflight must not cost these steps the
    # safe-to-run-in-any-consumer contract their docstrings promise.
    step.body(MockContext(run=Result(stdout="", exited=0)))

    with pytest.raises(Exit):
        step.body(MockContext(run={listing: Result(stdout=found, exited=0)}))
