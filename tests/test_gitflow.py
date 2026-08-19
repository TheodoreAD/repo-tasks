"""Tests for repo_tasks.gitflow: asserts the exact git command sequence each task builds via
invoke's MockContext, following test_quality.py's existing style. release_start/hotfix_start
exercise the real version.bump path with tag=False (MockContext's blanket run=True stub means
bump-my-version itself never actually runs, so the resulting branch name is this repo's real
pyproject.toml version — same fixture value test_version.py relies on)."""

import pytest
from invoke import MockContext, Result

from repo_tasks import gitflow


def _finish_context(current_branch):
    """MockContext's dict-keyed `run` only stubs exact command matches (unlike `run=True`'s
    blanket stub) — every git command _finish invokes needs its own entry."""
    return MockContext(
        run={
            "git rev-parse --abbrev-ref HEAD": Result(stdout=f"{current_branch}\n", exited=0),
            "git checkout main": Result(exited=0),
            "git checkout develop": Result(exited=0),
            f"git merge --no-ff {current_branch}": Result(exited=0),
            f"git branch -d {current_branch}": Result(exited=0),
            f"git tag v{current_branch.split('/', 1)[1]}": Result(exited=0),
            "git push origin main develop": Result(exited=0),
            f"git push origin v{current_branch.split('/', 1)[1]}": Result(exited=0),
        }
    )


def test_feature_start():
    c = MockContext(run=True)
    gitflow.feature_start.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git checkout -b feature/foo develop", echo=True
    )


def test_feature_finish():
    c = MockContext(run=True)
    gitflow.feature_finish.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff feature/foo",), {"echo": True}),
        (("git branch -d feature/foo",), {"echo": True}),
    ]


def test_release_start_checks_out_develop_before_bumping_then_branches():
    c = MockContext(run=True)
    gitflow.release_start.body(c, bump="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    # checkout develop MUST happen before the bump, or the bump commit lands on the wrong branch
    # and the release branch gets cut from an unbumped develop — a real bug the manual dry run
    # caught that call_strings[-2:] alone (checking only the tail) didn't.
    assert call_strings[0] == "git checkout develop"
    assert "--config-file" in call_strings[1]  # the underlying version.bump call, tag=False
    assert call_strings[2] == "git checkout -b release/0.1.0"


def test_hotfix_start_checks_out_main_before_bumping_then_branches():
    c = MockContext(run=True)
    gitflow.hotfix_start.body(c, bump="patch")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[0] == "git checkout main"
    assert "--config-file" in call_strings[1]
    assert call_strings[2] == "git checkout -b hotfix/0.1.0"


def test_release_finish_merges_tags_and_deletes():
    c = _finish_context("release/0.2.0")
    gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue] — [0] is the rev-parse query
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git tag v0.2.0",), {"echo": True}),
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git branch -d release/0.2.0",), {"echo": True}),
    ]


def test_release_finish_pushes_when_requested():
    c = _finish_context("release/0.2.0")
    gitflow.release_finish.body(c, push=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin main develop",), {"echo": True}),
        (("git push origin v0.2.0",), {"echo": True}),
    ]


def test_hotfix_finish_uses_hotfix_prefix():
    c = _finish_context("hotfix/0.1.1")
    gitflow.hotfix_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:4] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
    ]


def test_finish_raises_when_not_on_expected_branch_kind():
    c = MockContext(run={"git rev-parse --abbrev-ref HEAD": Result(stdout="main\n", exited=0)})
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
