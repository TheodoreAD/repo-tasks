"""Tests for repo_tasks.deps: asserts the exact command string each task builds via invoke's
MockContext — the only real logic here is flag-to-flag command construction."""

import pytest
from invoke.context import MockContext
from invoke.exceptions import Exit
from invoke.runners import Result

from repo_tasks import deps


def test_lock_default(c):
    deps.lock.body(c)
    c.run.assert_called_once_with("uv lock", echo=True, warn=True)


def test_lock_upgrade(c):
    deps.lock.body(c, upgrade=True)
    c.run.assert_called_once_with("uv lock --upgrade", echo=True, warn=True)


def test_lock_upgrade_package(c):
    deps.lock.body(c, package="repo-tasks")
    c.run.assert_called_once_with("uv lock --upgrade-package repo-tasks", echo=True, warn=True)


def test_lock_names_the_moved_member_and_the_retry_on_a_stale_editable_path(capsys):
    # Verbatim uv 0.11.19 output for a workspace member whose directory moved — the one `uv lock`
    # failure a plain re-run never fixes, so the task has to say what does.
    stderr = (
        "error: Failed to generate package metadata for `sample-service==0.1.0 @ editable+examples/sample-service`\n"
        "  Caused by: Distribution not found at: file:///repo/examples/sample-service\n"
    )
    c = MockContext(run=Result(stderr=stderr, exited=2))
    with pytest.raises(Exit) as exc_info:
        deps.lock.body(c)
    assert exc_info.value.code == 2
    assert "inv deps.lock --package sample-service" in capsys.readouterr().out


def test_lock_reraises_other_failures_without_a_hint(capsys):
    c = MockContext(run=Result(stderr="error: something else entirely\n", exited=1))
    with pytest.raises(Exit) as exc_info:
        deps.lock.body(c)
    assert exc_info.value.code == 1
    assert "Next steps" not in capsys.readouterr().out


def test_check():
    c = MockContext(run=Result())
    deps.check.body(c)
    c.run.assert_called_once_with("uv lock --check", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_list_default(c):
    deps.list.body(c)
    c.run.assert_called_once_with("uv pip list", echo=True)


def test_list_outdated(c):
    deps.list.body(c, outdated=True)
    c.run.assert_called_once_with("uv pip list --outdated", echo=True)


def test_tree_default(c):
    deps.tree.body(c)
    c.run.assert_called_once_with("uv tree", echo=True)


def test_tree_outdated(c):
    deps.tree.body(c, outdated=True)
    c.run.assert_called_once_with("uv tree --outdated", echo=True)


def test_export_default(c):
    deps.export.body(c)
    c.run.assert_called_once_with(
        "uv export --format requirements.txt --locked --no-editable -o requirements.txt", echo=True
    )


def test_export_no_dev_and_custom_output(c):
    deps.export.body(c, output="reqs/prod.txt", no_dev=True)
    c.run.assert_called_once_with(
        "uv export --format requirements.txt --locked --no-editable --no-dev -o reqs/prod.txt",
        echo=True,
    )
