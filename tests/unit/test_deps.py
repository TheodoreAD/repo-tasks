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
    workflow = (repo_root / ".github/workflows/security-reusable.yml").read_text(encoding="utf-8")

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


_STUBS_URL = "https://github.com/TheodoreAD/invoke-stubs"
_LOCKED = "ad052ca2c5ee" + "0" * 28
_HEAD = "f70ff01e14ef" + "0" * 28

# Real `uv tree --outdated --depth 1 --only-group dev` shape: a workspace root with no children, the
# project's own root, then one line per package, `(latest: ...)` only where the lock is behind and
# never on a git source.
_TREE = """sample-service v0.1.0
consumer v1.0.0
├── invoke-stubs v0.1.0 (group: dev)
├── pytest v9.1.1 (group: dev)
└── ruff v0.16.2 (group: dev) (latest: v0.16.9)
"""


def _currency_repo(tmp_cwd: Path, monkeypatch: pytest.MonkeyPatch, head: Result) -> MockContext:
    (tmp_cwd / "uv.lock").write_text(
        f'[[package]]\nname = "invoke-stubs"\nversion = "0.1.0"\nsource = {{ git = "{_STUBS_URL}#{_LOCKED}" }}\n\n'
        '[[package]]\nname = "ruff"\nversion = "0.16.2"\nsource = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(deps, "quality_dep_names", lambda: ["invoke-stubs", "pytest", "ruff", "zizmor"])
    return MockContext(
        run={deps._CURRENCY_TREE_CMD: Result(stdout=_TREE, exited=0), f"git ls-remote {_STUBS_URL} HEAD": head}
    )


def test_check_currency_names_what_the_lock_holds_behind(tmp_cwd, monkeypatch, capsys):
    """The case that asked for it: a git entry frozen at its first commit, which `configs.diff` calls
    up to date because it is declared."""
    c = _currency_repo(tmp_cwd, monkeypatch, Result(stdout=f"{_HEAD}\tHEAD\n", exited=0))
    deps.check_currency.body(c)
    out = capsys.readouterr().out
    assert f"invoke-stubs 0.1.0  BEHIND — git, locked at {_LOCKED[:12]}, default branch is at {_HEAD[:12]}" in out
    assert "ruff 0.16.2  BEHIND — latest 0.16.9" in out
    assert "pytest 9.1.1  current" in out
    # Declared-or-not is configs.diff's question; this one only says so and moves on.
    assert "zizmor  not in this project's dev group" in out
    assert "2 of 4 manifest entries behind" in out
    assert "inv deps.lock --package invoke-stubs" in out


def test_check_currency_calls_a_git_entry_at_its_head_current(tmp_cwd, monkeypatch, capsys):
    c = _currency_repo(tmp_cwd, monkeypatch, Result(stdout=f"{_LOCKED}\tHEAD\n", exited=0))
    deps.check_currency.body(c)
    assert "current with its default branch" in capsys.readouterr().out


def test_check_currency_does_not_invent_a_verdict_for_an_unreachable_remote(tmp_cwd, monkeypatch, capsys):
    c = _currency_repo(tmp_cwd, monkeypatch, Result(stderr="fatal: could not read", exited=128))
    deps.check_currency.body(c)
    out = capsys.readouterr().out
    assert f"could not read {_STUBS_URL}'s head" in out
    assert "1 of 4 manifest entries behind" in out  # ruff only


def test_check_currency_noops_without_a_lock(tmp_cwd, capsys):
    deps.check_currency.body(MockContext())
    assert "no uv.lock — nothing to check" in capsys.readouterr().out


def test_check_currency_stops_on_a_stale_lock(tmp_cwd, monkeypatch):
    (tmp_cwd / "uv.lock").write_text("", encoding="utf-8")
    monkeypatch.setattr(deps, "quality_dep_names", lambda: ["ruff"])
    c = MockContext(run={deps._CURRENCY_TREE_CMD: Result(stderr="The lockfile needs to be updated", exited=2)})
    with pytest.raises(Exit, match="lockfile needs to be updated"):
        deps.check_currency.body(c)
