"""Tests for repo_tasks.deps: asserts the exact command string each task builds via invoke's
MockContext — the only real logic here is flag-to-flag command construction."""

from pathlib import Path

import pytest
from invoke import Exit, MockContext, Result

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
    # A gate step: echoed and with no `hide`, so report mode reports and folds it (see runner.py).
    # `lock` above passes warn=True instead, because its failure path reads stderr for the
    # moved-member hint — the runner replays a failure either way, but only raises for this one.
    c.run.assert_called_once_with("uv lock --check", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_audit(c):
    deps.audit.body(c)
    c.run.assert_called_once_with("uv audit --locked", echo=True)


def test_audit_command_matches_the_reusable_workflow():
    """The security workflow runs the audit command directly rather than through `inv deps.audit`,
    so it needs nothing installed — see the reasoning in security-reusable.yml. That makes the
    command string live in two places, and this is what keeps them from drifting apart: change one
    and this fails naming the other."""
    c = MockContext(run=True)
    deps.audit.body(c)
    command = c.run.call_args[0][0]  # pyright: ignore[reportAttributeAccessIssue]

    # Anchored to this file, not to cwd: the tier's `tmp_cwd` fixture means cwd is not dependable,
    # and this is the repo's own workflow rather than a scratch fixture.
    repo_root = Path(__file__).parents[2]
    workflow = (repo_root / ".github/workflows/security-reusable.yml").read_text()

    assert f"- run: {command}\n" in workflow, (
        f"deps.audit runs {command!r}, which security-reusable.yml does not. Update the workflow's "
        f"`run:` step to match, or the audit CI performs stops being the audit this task defines."
    )


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
