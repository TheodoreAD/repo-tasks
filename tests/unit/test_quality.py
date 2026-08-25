"""Tests for repo_tasks.quality: asserts the exact command string each task
builds via invoke's MockContext, plus dedicated coverage for _sh_files — the
one piece of real logic, and what makes the mandatory `check`/`fix` composite
safe to run unconditionally on a repo with no shell scripts."""

from invoke.context import MockContext
from invoke.runners import Result

from repo_tasks import quality

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
