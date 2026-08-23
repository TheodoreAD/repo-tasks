"""Tests for repo_tasks.deps: asserts the exact command string each task builds via invoke's
MockContext — the only real logic here is flag-to-flag command construction."""

from invoke import MockContext, Result

from repo_tasks import deps


def test_lock_default(c):
    deps.lock.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv lock", echo=True)


def test_lock_upgrade(c):
    deps.lock.body(c, upgrade=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv lock --upgrade", echo=True)


def test_lock_upgrade_package(c):
    deps.lock.body(c, package="repo-tasks")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv lock --upgrade-package repo-tasks", echo=True)


def test_check():
    c = MockContext(run=Result())
    deps.check.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv lock --check", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_list_default(c):
    deps.list.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv pip list", echo=True)


def test_list_outdated(c):
    deps.list.body(c, outdated=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv pip list --outdated", echo=True)


def test_tree_default(c):
    deps.tree.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv tree", echo=True)


def test_tree_outdated(c):
    deps.tree.body(c, outdated=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv tree --outdated", echo=True)


def test_export_default(c):
    deps.export.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(
        "uv export --format requirements.txt --locked --no-editable -o requirements.txt", echo=True
    )


def test_export_no_dev_and_custom_output(c):
    deps.export.body(c, output="reqs/prod.txt", no_dev=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(
        "uv export --format requirements.txt --locked --no-editable --no-dev -o reqs/prod.txt",
        echo=True,
    )
