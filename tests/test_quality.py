"""Tests for repo_tasks.quality: asserts the exact command string each task
builds via invoke's MockContext, plus dedicated coverage for _sh_files — the
one piece of real logic, and what makes the mandatory `check`/`fix` composite
safe to run unconditionally on a repo with no shell scripts."""

from invoke import MockContext, Result

from repo_tasks import quality


def test_lint_check():
    c = MockContext(run=True)
    quality.lint_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess] — invoke's untyped Task.body
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue] — MockContext wraps run in a Mock
        "ruff check .", echo=True
    )


def test_lint_apply():
    c = MockContext(run=True)
    quality.lint_apply.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "ruff check --fix .", echo=True
    )


def test_format_check():
    c = MockContext(run=True)
    quality.format_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("ruff format --check .",), {"echo": True}),
        (("dprint check --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_format_apply():
    c = MockContext(run=True)
    quality.format_apply.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("ruff format .",), {"echo": True}),
        (("dprint fmt --config-discovery=ignore-descendants",), {"echo": True}),
    ]


def test_type_check():
    c = MockContext(run=True)
    quality.type_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("basedpyright", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_test():
    c = MockContext(run=True)
    quality.test.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("pytest", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_sh_files_empty():
    c = MockContext(run=Result(stdout="", exited=0))
    assert quality._sh_files(c) == []  # pyright: ignore[reportPrivateUsage] — testing the one piece of real logic directly


def test_sh_files_nonempty():
    c = MockContext(run=Result(stdout="./a.sh ./b.sh\n", exited=0))
    assert quality._sh_files(c) == ["./a.sh", "./b.sh"]  # pyright: ignore[reportPrivateUsage]


def test_sh_files_command_failure_treated_as_empty():
    c = MockContext(run=Result(exited=1))
    assert quality._sh_files(c) == []  # pyright: ignore[reportPrivateUsage]


def test_shell_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "fd -e sh .", hide=True, warn=True
    )


def test_shell_check_runs_shellcheck_when_files_found():
    c = MockContext(
        run={
            "fd -e sh .": Result(stdout="./a.sh\n", exited=0),
            "shellcheck ./a.sh": Result(exited=0),
        }
    )
    quality.shell_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shellcheck ./a.sh",),
        {"echo": True},
    )


def test_shell_format_check_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "fd -e sh .", hide=True, warn=True
    )


def test_shell_format_apply_noop_when_no_sh_files():
    c = MockContext(run=Result(stdout="", exited=0))
    quality.shell_format_apply.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "fd -e sh .", hide=True, warn=True
    )


def test_shell_format_apply_runs_shfmt_when_files_found():
    c = MockContext(
        run={
            "fd -e sh .": Result(stdout="./a.sh\n", exited=0),
            "shfmt -w ./a.sh": Result(exited=0),
        }
    )
    quality.shell_format_apply.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-1] == (  # pyright: ignore[reportAttributeAccessIssue]
        ("shfmt -w ./a.sh",),
        {"echo": True},
    )
